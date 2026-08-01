from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT_PATH = Path("assets/github-activity.svg")

USERNAME = os.getenv("GITHUB_USERNAME", "antonisloukis")
TOKEN = os.getenv("GITHUB_TOKEN")


BLUE = "#58A6FF"
TEXT = "#F0F6FC"
MUTED = "#8B949E"
LINE = "#30363D"
BACKGROUND = "#0D1117"


PROFILE_QUERY = """
query Profile($login: String!) {
  user(login: $login) {
    pullRequests(first: 1) {
      totalCount
    }

    issues(first: 1) {
      totalCount
    }

    contributionsCollection {
      contributionYears
    }

    repositories(
      first: 100
      ownerAffiliations: OWNER
      privacy: PUBLIC
      isFork: false
      orderBy: {
        field: UPDATED_AT
        direction: DESC
      }
    ) {
      nodes {
        stargazerCount

        languages(
          first: 10
          orderBy: {
            field: SIZE
            direction: DESC
          }
        ) {
          edges {
            size

            node {
              name
              color
            }
          }
        }
      }
    }
  }
}
"""


CONTRIBUTIONS_QUERY = """
query Contributions(
  $login: String!
  $from: DateTime!
  $to: DateTime!
) {
  user(login: $login) {
    contributionsCollection(
      from: $from
      to: $to
    ) {
      totalCommitContributions

      contributionCalendar {
        totalContributions

        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class ProfileStats:
    stars: int
    commits: int
    pull_requests: int
    issues: int
    contributed_this_year: int
    total_contributions: int
    current_streak: int
    longest_streak: int
    languages: list[tuple[str, int, str]]


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def graphql_request(
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing.")

    payload = json.dumps(
        {
            "query": query,
            "variables": variables,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "antonisloukis-profile-stats",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        response_body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"GitHub API returned HTTP "
            f"{error.code}: {response_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not contact GitHub API: {error}"
        ) from error

    if result.get("errors"):
        raise RuntimeError(
            f"GraphQL errors: {result['errors']}"
        )

    return result["data"]


def contribution_period(
    year: int,
    now: datetime,
) -> tuple[str, str]:
    start = datetime(
        year,
        1,
        1,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )

    if year == now.year:
        end = now
    else:
        end = datetime(
            year,
            12,
            31,
            23,
            59,
            59,
            tzinfo=timezone.utc,
        )

    return start.isoformat(), end.isoformat()


def calculate_streaks(
    contribution_days: list[dict[str, Any]],
) -> tuple[int, int]:
    contributions: dict[date, int] = {}

    for day in contribution_days:
        parsed_date = datetime.strptime(
            day["date"],
            "%Y-%m-%d",
        ).date()

        contributions[parsed_date] = int(
            day["contributionCount"]
        )

    if not contributions:
        return 0, 0

    longest_streak = 0
    running_streak = 0

    for current_date in sorted(contributions):
        if contributions[current_date] > 0:
            running_streak += 1

            longest_streak = max(
                longest_streak,
                running_streak,
            )
        else:
            running_streak = 0

    today = datetime.now(timezone.utc).date()
    cursor = today

    # A streak remains active when the last contribution
    # was made yesterday.
    if contributions.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)

    current_streak = 0

    while contributions.get(cursor, 0) > 0:
        current_streak += 1
        cursor -= timedelta(days=1)

    return current_streak, longest_streak


def collect_languages(
    repositories: list[dict[str, Any]],
) -> list[tuple[str, int, str]]:
    language_sizes: Counter[str] = Counter()
    language_colors: dict[str, str] = {}

    for repository in repositories:
        language_edges = repository[
            "languages"
        ]["edges"]

        for edge in language_edges:
            language_name = edge["node"]["name"]
            language_size = int(edge["size"])

            language_color = (
                edge["node"].get("color")
                or BLUE
            )

            language_sizes[language_name] += (
                language_size
            )

            language_colors[language_name] = (
                language_color
            )

    return [
        (
            language_name,
            language_size,
            language_colors[language_name],
        )
        for language_name, language_size
        in language_sizes.most_common(5)
    ]


def fetch_stats() -> ProfileStats:
    now = datetime.now(timezone.utc)

    profile_result = graphql_request(
        PROFILE_QUERY,
        {
            "login": USERNAME,
        },
    )

    user = profile_result.get("user")

    if user is None:
        raise RuntimeError(
            f"GitHub user '{USERNAME}' was not found."
        )

    repositories = user["repositories"]["nodes"]

    total_stars = sum(
        int(repository["stargazerCount"])
        for repository in repositories
    )

    contribution_years = sorted(
        set(
            user[
                "contributionsCollection"
            ]["contributionYears"]
        )
    )

    if now.year not in contribution_years:
        contribution_years.append(now.year)

    total_commits = 0
    total_contributions = 0
    contributed_this_year = 0

    all_contribution_days: list[
        dict[str, Any]
    ] = []

    for year in contribution_years:
        start, end = contribution_period(
            year,
            now,
        )

        contribution_result = graphql_request(
            CONTRIBUTIONS_QUERY,
            {
                "login": USERNAME,
                "from": start,
                "to": end,
            },
        )

        collection = contribution_result[
            "user"
        ]["contributionsCollection"]

        calendar = collection[
            "contributionCalendar"
        ]

        total_commits += int(
            collection[
                "totalCommitContributions"
            ]
        )

        total_contributions += int(
            calendar["totalContributions"]
        )

        if year == now.year:
            contributed_this_year = int(
                calendar["totalContributions"]
            )

        for week in calendar["weeks"]:
            all_contribution_days.extend(
                week["contributionDays"]
            )

    current_streak, longest_streak = (
        calculate_streaks(
            all_contribution_days
        )
    )

    return ProfileStats(
        stars=total_stars,
        commits=total_commits,
        pull_requests=int(
            user["pullRequests"]["totalCount"]
        ),
        issues=int(
            user["issues"]["totalCount"]
        ),
        contributed_this_year=(
            contributed_this_year
        ),
        total_contributions=(
            total_contributions
        ),
        current_streak=current_streak,
        longest_streak=longest_streak,
        languages=collect_languages(
            repositories
        ),
    )


def star_icon(
    x: int,
    y: int,
) -> str:
    return (
        f'<text x="{x}" y="{y}" '
        f'class="star-icon">★</text>'
    )


def commit_icon(
    x: int,
    y: int,
) -> str:
    return f"""
    <g transform="translate({x},{y})"
       fill="none"
       stroke="#3FB950"
       stroke-width="2.4"
       stroke-linecap="round"
       stroke-linejoin="round">

      <path d="
        M7 3
        1 9
        l6 6

        M17 3
        l6 6
        -6 6

        M14 1
        10 17
      "/>
    </g>
    """


def pull_request_icon(
    x: int,
    y: int,
) -> str:
    return f"""
    <g transform="translate({x},{y})"
       fill="none"
       stroke="#A371F7"
       stroke-width="2.2"
       stroke-linecap="round"
       stroke-linejoin="round">

      <circle cx="4" cy="4" r="2.5"/>
      <circle cx="4" cy="18" r="2.5"/>
      <circle cx="20" cy="18" r="2.5"/>

      <path d="
        M4 6.5
        v9

        M8 4
        h5
        a7 7 0 0 1 7 7
        v4.5

        M10 1
        7 4
        l3 3
      "/>
    </g>
    """


def issue_icon(
    x: int,
    y: int,
) -> str:
    return f"""
    <g transform="translate({x},{y})">

      <circle
        cx="11"
        cy="11"
        r="9"
        fill="none"
        stroke="#58A6FF"
        stroke-width="2.4"
      />

      <circle
        cx="11"
        cy="11"
        r="2.2"
        fill="#58A6FF"
      />
    </g>
    """


def calendar_icon(
    x: int,
    y: int,
) -> str:
    return f"""
    <g transform="translate({x},{y})"
       fill="none"
       stroke="#F0883E"
       stroke-width="2.2"
       stroke-linecap="round"
       stroke-linejoin="round">

      <rect
        x="1"
        y="4"
        width="20"
        height="17"
        rx="2"
      />

      <path d="
        M6 1
        v6

        M16 1
        v6

        M1 9
        h20
      "/>
    </g>
    """


def bottom_icon(
    icon_type: str,
    x: int,
    y: int,
) -> str:
    if icon_type == "people":
        icon_path = """
        <circle cx="12" cy="7" r="4"/>

        <path d="
          M4 23
          v-2
          a8 8 0 0 1 16 0
          v2
        "/>

        <circle cx="3" cy="10" r="3"/>

        <path d="
          M-2 22
          v-1
          a6 6 0 0 1 5-6
        "/>

        <circle cx="21" cy="10" r="3"/>

        <path d="
          M26 22
          v-1
          a6 6 0 0 0-5-6
        "/>
        """

    elif icon_type == "flame":
        icon_path = """
        <path d="
          M12 24
          c6 0 10-4 10-10
          0-4-2-7-6-11
          0 5-3 7-5 9
          -1-3-2-5-1-8
          C5 8 3 12 3 16
          c0 5 4 8 9 8Z
        "/>

        <path d="
          M9 19
          c0-2 1-4 4-6
          0 3 2 4 2 6
          0 2-1 3-3 3
          s-3-1-3-3Z
        "/>
        """

    else:
        icon_path = """
        <path d="
          M7 2
          h10
          v6
          c0 5-2 8-5 8
          s-5-3-5-8Z
        "/>

        <path d="
          M7 5
          H2
          v2
          c0 4 2 6 6 6

          M17 5
          h5
          v2
          c0 4-2 6-6 6

          M12 16
          v5

          M7 23
          h10
        "/>
        """

    return f"""
    <g transform="translate({x},{y})"
       fill="none"
       stroke="{BLUE}"
       stroke-width="2.2"
       stroke-linecap="round"
       stroke-linejoin="round">

      {icon_path}
    </g>
    """


def statistic_row(
    y: int,
    label: str,
    value: int,
    icon: str,
    show_divider: bool = True,
) -> str:
    divider = ""

    if show_divider:
        divider = f"""
        <line
          x1="50"
          y1="{y + 26}"
          x2="414"
          y2="{y + 26}"
          stroke="{LINE}"
        />
        """

    return f"""
    {icon}

    <text
      x="92"
      y="{y}"
      class="stat-label">
      {escape(label)}
    </text>

    <text
      x="414"
      y="{y}"
      text-anchor="end"
      class="stat-value">
      {value:,}
    </text>

    {divider}
    """


def language_markup(
    languages: list[tuple[str, int, str]],
) -> str:
    if not languages:
        return """
        <text
          x="484"
          y="95"
          class="muted">
          No language data available yet.
        </text>
        """

    total_size = sum(
        size
        for _, size, _
        in languages
    )

    bar_x = 484
    bar_y = 88
    bar_width = 356

    parts = [
        f"""
        <rect
          x="{bar_x}"
          y="{bar_y}"
          width="{bar_width}"
          height="4"
          rx="2"
          fill="#21262D"
        />
        """
    ]

    cursor = bar_x

    for language_name, size, color in languages:
        segment_width = (
            size / total_size
        ) * bar_width

        parts.append(
            f"""
            <rect
              x="{cursor:.2f}"
              y="{bar_y}"
              width="{max(segment_width, 1.5):.2f}"
              height="4"
              fill="{escape(color)}"
            />
            """
        )

        cursor += segment_width

    for index, (
        language_name,
        size,
        color,
    ) in enumerate(languages):
        percentage = (
            size / total_size
        ) * 100

        y = 120 + index * 27

        parts.append(
            f"""
            <circle
              cx="490"
              cy="{y - 4}"
              r="4.5"
              fill="{escape(color)}"
            />

            <text
              x="504"
              y="{y}"
              class="language-label">
              {escape(language_name)}
            </text>

            <text
              x="840"
              y="{y}"
              text-anchor="end"
              class="language-value">
              {percentage:.1f}%
            </text>
            """
        )

    return "\n".join(parts)


def generate_svg(
    stats: ProfileStats,
) -> str:
    updated_at = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    rows = "\n".join(
        [
            statistic_row(
                88,
                "Total stars earned",
                stats.stars,
                star_icon(61, 94),
            ),

            statistic_row(
                132,
                "Total commits",
                stats.commits,
                commit_icon(60, 116),
            ),

            statistic_row(
                176,
                "Total PRs",
                stats.pull_requests,
                pull_request_icon(60, 158),
            ),

            statistic_row(
                220,
                "Total issues",
                stats.issues,
                issue_icon(60, 202),
            ),

            statistic_row(
                264,
                "Contributed this year",
                stats.contributed_this_year,
                calendar_icon(60, 246),
                show_divider=False,
            ),
        ]
    )

    languages = language_markup(
        stats.languages
    )

    return f"""
<svg
  xmlns="http://www.w3.org/2000/svg"
  width="900"
  height="425"
  viewBox="0 0 900 425"
  role="img"
  aria-labelledby="title description">

  <title id="title">
    {escape(USERNAME)} GitHub statistics
  </title>

  <desc id="description">
    Automatically updated GitHub statistics,
    languages and contribution streaks.
  </desc>

  <style>
    .section-title {{
      font:
        700 16.5px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {TEXT};
    }}

    .stat-label {{
      font:
        600 12px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {TEXT};
    }}

    .stat-value {{
      font:
        700 13px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {TEXT};
    }}

    .language-label {{
      font:
        600 12px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {TEXT};
    }}

    .language-value {{
      font:
        700 12px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {TEXT};
    }}

    .metric-number {{
      font:
        700 27px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {BLUE};
    }}

    .metric-label {{
      font:
        500 12px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: #C9D1D9;
    }}

    .muted {{
      font:
        400 10px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {MUTED};
    }}

    .star-icon {{
      font:
        700 25px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI Symbol",
        sans-serif;

      fill: #F2CC60;
    }}
  </style>

  <!-- Dark background without an outer border -->

  <rect
    width="900"
    height="425"
    rx="18"
    fill="{BACKGROUND}"
  />

  <!-- Section headings -->

  <text
    x="50"
    y="38"
    class="section-title">
    GitHub Stats
  </text>

  <text
    x="484"
    y="38"
    class="section-title">
    Most Used Languages
  </text>

  <!-- Internal divider lines -->

  <line
    x1="50"
    y1="53"
    x2="414"
    y2="53"
    stroke="{LINE}"
  />

  <line
    x1="484"
    y1="53"
    x2="840"
    y2="53"
    stroke="{LINE}"
  />

  <line
    x1="450"
    y1="28"
    x2="450"
    y2="292"
    stroke="{LINE}"
  />

  <!-- Statistics -->

  {rows}

  <!-- Languages -->

  {languages}

  <!-- Bottom divider -->

  <line
    x1="42"
    y1="309"
    x2="858"
    y2="309"
    stroke="{LINE}"
  />

  <line
    x1="300"
    y1="329"
    x2="300"
    y2="401"
    stroke="{LINE}"
  />

  <line
    x1="600"
    y1="329"
    x2="600"
    y2="401"
    stroke="{LINE}"
  />

  <!-- Total contributions -->

  {bottom_icon("people", 138, 326)}

  <text
    x="150"
    y="375"
    text-anchor="middle"
    class="metric-number">
    {stats.total_contributions:,}
  </text>

  <text
    x="150"
    y="399"
    text-anchor="middle"
    class="metric-label">
    Total contributions
  </text>

  <!-- Current streak -->

  {bottom_icon("flame", 438, 326)}

  <text
    x="450"
    y="375"
    text-anchor="middle"
    class="metric-number">
    {stats.current_streak}
  </text>

  <text
    x="450"
    y="399"
    text-anchor="middle"
    class="metric-label">
    Current streak
  </text>

  <!-- Longest streak -->

  {bottom_icon("trophy", 738, 326)}

  <text
    x="750"
    y="375"
    text-anchor="middle"
    class="metric-number">
    {stats.longest_streak}
  </text>

  <text
    x="750"
    y="399"
    text-anchor="middle"
    class="metric-label">
    Longest streak
  </text>

  <!-- Updated time -->

  <text
    x="858"
    y="417"
    text-anchor="end"
    class="muted">
    Updated {escape(updated_at)}
  </text>

</svg>
"""


def main() -> int:
    try:
        stats = fetch_stats()
        svg = generate_svg(stats)

        OUTPUT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        OUTPUT_PATH.write_text(
            svg,
            encoding="utf-8",
        )

        print(
            f"Updated {OUTPUT_PATH}"
        )

        return 0

    except Exception as error:
        print(
            f"Error: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
