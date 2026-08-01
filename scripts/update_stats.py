from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT_PATH = Path("assets/github-activity.svg")

USERNAME = os.getenv("GITHUB_USERNAME", "antonisloukis")
TOKEN = os.getenv("GITHUB_TOKEN")

BG = "#0d1117"
BLUE = "#58a6ff"
WHITE = "#e6edf3"
MUTED = "#8b949e"
LINE = "#21262d"


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
          first: 20
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


def esc(value: object) -> str:
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
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"GitHub API returned HTTP "
            f"{error.code}: {body}"
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
    counts: dict[date, int] = {}

    for item in contribution_days:
        current_date = datetime.strptime(
            item["date"],
            "%Y-%m-%d",
        ).date()

        counts[current_date] = int(
            item["contributionCount"]
        )

    if not counts:
        return 0, 0

    longest = 0
    running = 0

    for current_date in sorted(counts):
        if counts[current_date] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    cursor = datetime.now(
        timezone.utc
    ).date()

    # Keep yesterday's streak active when there
    # has not been a contribution today yet.
    if counts.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)

    current = 0

    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    return current, longest


def collect_languages(
    repositories: list[dict[str, Any]],
) -> list[tuple[str, float, str]]:
    sizes: Counter[str] = Counter()
    colors: dict[str, str] = {}

    for repository in repositories:
        language_edges = repository[
            "languages"
        ]["edges"]

        for edge in language_edges:
            name = edge["node"]["name"]
            size = int(edge["size"])

            color = (
                edge["node"].get("color")
                or BLUE
            )

            sizes[name] += size
            colors[name] = color

    total = sum(sizes.values())

    if total <= 0:
        return []

    ranked = sizes.most_common()

    if len(ranked) <= 6:
        displayed = [
            (
                name,
                size,
                colors[name],
            )
            for name, size in ranked
        ]

    else:
        displayed = [
            (
                name,
                size,
                colors[name],
            )
            for name, size in ranked[:5]
        ]

        other_size = sum(
            size
            for _, size in ranked[5:]
        )

        displayed.append(
            (
                "Other",
                other_size,
                MUTED,
            )
        )

    return [
        (
            name,
            size / total * 100,
            color,
        )
        for name, size, color in displayed
    ]


def fetch_stats() -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    profile = graphql_request(
        PROFILE_QUERY,
        {
            "login": USERNAME,
        },
    )

    user = profile.get("user")

    if user is None:
        raise RuntimeError(
            f"GitHub user '{USERNAME}' "
            "was not found."
        )

    repositories = user[
        "repositories"
    ]["nodes"]

    years = sorted(
        set(
            user[
                "contributionsCollection"
            ]["contributionYears"]
        )
    )

    if now.year not in years:
        years.append(now.year)

    total_commits = 0
    total_contributions = 0
    contributed_this_year = 0

    all_days: list[dict[str, Any]] = []

    for year in years:
        start, end = contribution_period(
            year,
            now,
        )

        contribution_data = graphql_request(
            CONTRIBUTIONS_QUERY,
            {
                "login": USERNAME,
                "from": start,
                "to": end,
            },
        )

        collection = contribution_data[
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
            calendar[
                "totalContributions"
            ]
        )

        if year == now.year:
            contributed_this_year = int(
                calendar[
                    "totalContributions"
                ]
            )

        for week in calendar["weeks"]:
            all_days.extend(
                week["contributionDays"]
            )

    current_streak, longest_streak = (
        calculate_streaks(all_days)
    )

    total_stars = sum(
        int(
            repository[
                "stargazerCount"
            ]
        )
        for repository in repositories
    )

    return {
        "total_stars": total_stars,
        "total_commits": total_commits,
        "total_prs": int(
            user[
                "pullRequests"
            ]["totalCount"]
        ),
        "total_issues": int(
            user[
                "issues"
            ]["totalCount"]
        ),
        "contributed_this_year": (
            contributed_this_year
        ),
        "total_contributions": (
            total_contributions
        ),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "languages": collect_languages(
            repositories
        ),
    }


ICON_PATHS = {
    "star": """
      <path
        d="
          M12 2.5
          l2.8 5.7
          6.2.9
          -4.5 4.4
          1.1 6.2
          L12 16.8
          6.4 19.7
          l1.1-6.2
          L3 9.1
          l6.2-.9
          L12 2.5
          z
        "
      />
    """,

    "commit": """
      <path
        d="
          M12 4
          a8 8 0 1 1-5.7 2.3
        "
      />

      <path
        d="
          M4.2 3.8
          H8
          v3.8
        "
      />
    """,

    "pr": """
      <circle cx="7" cy="5" r="2"/>
      <circle cx="17" cy="19" r="2"/>
      <circle cx="17" cy="5" r="2"/>

      <path
        d="
          M7 7
          v10
          a2 2 0 0 0 2 2
          h6
        "
      />

      <path
        d="
          M15 5
          h-4
          a2 2 0 0 0-2 2
          v2
        "
      />
    """,

    "issue": """
      <circle cx="12" cy="12" r="8"/>

      <path
        d="
          M12 7.5
          v5
        "
      />

      <circle
        cx="12"
        cy="15.8"
        r="1"
        fill="#58a6ff"
        stroke="none"
      />
    """,

    "calendar": """
      <rect
        x="4"
        y="6"
        width="16"
        height="14"
        rx="1.8"
      />

      <path
        d="
          M4 10
          h16

          M8 3.8
          v4

          M16 3.8
          v4
        "
      />
    """,

    "people": """
      <circle cx="9" cy="9" r="2.3"/>
      <circle cx="15" cy="9" r="2.3"/>

      <path
        d="
          M5.5 18
          c.8-2.6 2.6-4 5.5-4
          s4.7 1.4 5.5 4
        "
      />

      <path
        d="
          M2.8 18
          c.6-1.8 1.7-2.8 3.2-3.3

          M21.2 18
          c-.6-1.8-1.7-2.8-3.2-3.3
        "
      />
    """,

    "flame": """
      <path
        d="
          M12 3.5
          c1.5 2.3 3.8 4 3.8 7.1

          A3.8 3.8 0 1 1 8.2 11

          c0-1.9 1-3.4 2.4-4.8

          .2 1.6.9 2.7 1.4 3.2

          .8-1.1 1-2.7 0-5.9
          z
        "
      />
    """,

    "trophy": """
      <path
        d="
          M8 5
          h8
          v3
          a4 4 0 0 1-8 0
          V5
          z
        "
      />

      <path
        d="
          M6 6
          H4
          a2 2 0 0 0 2 3

          M18 6
          h2
          a2 2 0 0 1-2 3
        "
      />

      <path
        d="
          M12 12
          v4

          M9 20
          h6
        "
      />
    """,
}


def icon(
    name: str,
    x: int,
    y: int,
    scale: float = 1.0,
) -> str:
    return f"""
    <g
      transform="translate({x},{y}) scale({scale})"
      fill="none"
      stroke="{BLUE}"
      stroke-width="1.9"
      stroke-linecap="round"
      stroke-linejoin="round">

      {ICON_PATHS[name]}

    </g>
    """


def stat_row(
    icon_name: str,
    label: str,
    value: int,
    y: int,
    left_x: int,
    value_x: int,
) -> str:
    return f"""
    {icon(
        icon_name,
        left_x,
        y - 21,
    )}

    <text
      x="{left_x + 38}"
      y="{y}"
      class="stat-label">
      {esc(label)}
    </text>

    <text
      x="{value_x}"
      y="{y}"
      text-anchor="end"
      class="stat-value">
      {value:,}
    </text>
    """


def build_language_svg(
    languages: list[
        tuple[str, float, str]
    ],
    bar_x: int,
    bar_y: int,
    bar_width: int,
    bar_height: int,
) -> tuple[str, str]:
    if not languages:
        languages = [
            (
                "No data",
                100.0,
                MUTED,
            )
        ]

    segments: list[str] = []
    legend: list[str] = []

    cursor = float(bar_x)

    for index, (
        name,
        percentage,
        color,
    ) in enumerate(languages):
        if index == len(languages) - 1:
            segment_width = (
                bar_x
                + bar_width
                - cursor
            )
        else:
            segment_width = (
                bar_width
                * percentage
                / 100
            )

        segments.append(
            f"""
            <rect
              x="{cursor:.2f}"
              y="{bar_y}"
              width="{max(
                  segment_width,
                  1.5,
              ):.2f}"
              height="{bar_height}"
              fill="{esc(color)}"
            />
            """
        )

        cursor += segment_width

        column = index % 2
        row = index // 2

        legend_x = (
            bar_x
            + column * 200
        )

        legend_y = (
            bar_y
            + 34
            + row * 31
        )

        legend.append(
            f"""
            <circle
              cx="{legend_x + 5}"
              cy="{legend_y - 5}"
              r="4"
              fill="{esc(color)}"
            />

            <text
              x="{legend_x + 17}"
              y="{legend_y}"
              class="legend-label">
              {esc(name)}
            </text>

            <text
              x="{legend_x + 175}"
              y="{legend_y}"
              text-anchor="end"
              class="legend-value">
              {percentage:.1f}%
            </text>
            """
        )

    return (
        "\n".join(segments),
        "\n".join(legend),
    )


def build_svg(
    stats: dict[str, Any],
) -> str:
    width = 1000
    height = 340

    left_x = 34
    left_value_x = 455
    right_x = 535

    title_y = 56

    row_y = [
        92,
        120,
        148,
        176,
        204,
    ]

    bar_x = right_x
    bar_y = 98
    bar_width = 405
    bar_height = 7

    (
        language_segments,
        language_legend,
    ) = build_language_svg(
        stats["languages"],
        bar_x,
        bar_y,
        bar_width,
        bar_height,
    )

    rows = "\n".join(
        [
            stat_row(
                "star",
                "Total Stars Earned:",
                stats["total_stars"],
                row_y[0],
                left_x,
                left_value_x,
            ),

            stat_row(
                "commit",
                "Total Commits:",
                stats["total_commits"],
                row_y[1],
                left_x,
                left_value_x,
            ),

            stat_row(
                "pr",
                "Total PRs:",
                stats["total_prs"],
                row_y[2],
                left_x,
                left_value_x,
            ),

            stat_row(
                "issue",
                "Total Issues:",
                stats["total_issues"],
                row_y[3],
                left_x,
                left_value_x,
            ),

            stat_row(
                "calendar",
                "Contributed (this year):",
                stats[
                    "contributed_this_year"
                ],
                row_y[4],
                left_x,
                left_value_x,
            ),
        ]
    )

    updated = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    return f"""<svg
  xmlns="http://www.w3.org/2000/svg"
  width="{width}"
  height="{height}"
  viewBox="0 0 {width} {height}"
  role="img"
  aria-labelledby="title description">

  <title id="title">
    {esc(USERNAME)} development metrics
  </title>

  <desc id="description">
    Automatically updated GitHub statistics,
    language usage and streaks.
  </desc>

  <defs>
    <clipPath id="language-bar-clip">
      <rect
        x="{bar_x}"
        y="{bar_y}"
        width="{bar_width}"
        height="{bar_height}"
        rx="{bar_height / 2}"
      />
    </clipPath>
  </defs>

  <style>
    .section-title {{
      font:
        400 18px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {BLUE};
    }}

    .stat-label,
    .stat-value {{
      font:
        700 14px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {WHITE};
    }}

    .legend-label {{
      font:
        400 12px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {WHITE};
    }}

    .legend-value {{
      font:
        700 12px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {WHITE};
    }}

    .metric-number {{
      font:
        700 24px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {BLUE};
    }}

    .metric-label {{
      font:
        600 13px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {WHITE};
    }}

    .updated {{
      font:
        400 11px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      fill: {MUTED};
    }}
  </style>

  <rect
    width="{width}"
    height="{height}"
    rx="16"
    fill="{BG}"
  />

  <text
    x="{left_x + 1}"
    y="{title_y}"
    class="section-title">
    GitHub Stats
  </text>

  <text
    x="{right_x}"
    y="{title_y}"
    class="section-title">
    Most Used Languages
  </text>

  <line
    x1="500"
    y1="34"
    x2="500"
    y2="218"
    stroke="{LINE}"
    stroke-width="1"
  />

  {rows}

  <rect
    x="{bar_x}"
    y="{bar_y}"
    width="{bar_width}"
    height="{bar_height}"
    rx="{bar_height / 2}"
    fill="#161b22"
  />

  <g clip-path="url(#language-bar-clip)">
    {language_segments}
  </g>

  {language_legend}

  <line
    x1="333"
    y1="232"
    x2="333"
    y2="315"
    stroke="{LINE}"
    stroke-width="1"
  />

  <line
    x1="667"
    y1="232"
    x2="667"
    y2="315"
    stroke="{LINE}"
    stroke-width="1"
  />

  {icon(
    "people",
    149,
    226,
    1.5,
)}

  <text
    x="167"
    y="278"
    text-anchor="middle"
    class="metric-number">
    {stats["total_contributions"]:,}
  </text>

  <text
    x="167"
    y="307"
    text-anchor="middle"
    class="metric-label">
    Total contributions
  </text>

  {icon(
    "flame",
    482,
    226,
    1.5,
)}

  <text
    x="500"
    y="278"
    text-anchor="middle"
    class="metric-number">
    {stats["current_streak"]}
  </text>

  <text
    x="500"
    y="307"
    text-anchor="middle"
    class="metric-label">
    Current streak
  </text>

  {icon(
    "trophy",
    816,
    226,
    1.5,
)}

  <text
    x="834"
    y="278"
    text-anchor="middle"
    class="metric-number">
    {stats["longest_streak"]}
  </text>

  <text
    x="834"
    y="307"
    text-anchor="middle"
    class="metric-label">
    Longest streak
  </text>

  <text
    x="958"
    y="327"
    text-anchor="end"
    class="updated">
    Updated {esc(updated)}
  </text>
</svg>
"""


def main() -> int:
    try:
        stats = fetch_stats()

        OUTPUT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        OUTPUT_PATH.write_text(
            build_svg(stats),
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
