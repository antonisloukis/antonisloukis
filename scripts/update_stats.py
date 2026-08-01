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


QUERY = """
query ProfileStats($login: String!) {
  user(login: $login) {
    followers {
      totalCount
    }

    repositories(
      first: 100
      ownerAffiliations: OWNER
      privacy: PUBLIC
      isFork: false
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      totalCount

      nodes {
        stargazerCount

        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
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

    contributionsCollection {
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


def graphql_request() -> dict[str, Any]:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing.")

    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {"login": USERNAME},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-svg-updater",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API returned HTTP {error.code}: {body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not contact GitHub API: {error}") from error

    if result.get("errors"):
        raise RuntimeError(f"GraphQL errors: {result['errors']}")

    user = result.get("data", {}).get("user")

    if user is None:
        raise RuntimeError(f"GitHub user '{USERNAME}' was not found.")

    return user


def calculate_streaks(
    contribution_days: list[dict[str, Any]],
) -> tuple[int, int]:
    contributions: dict[date, int] = {}

    for day in contribution_days:
        parsed_date = datetime.strptime(day["date"], "%Y-%m-%d").date()
        contributions[parsed_date] = int(day["contributionCount"])

    if not contributions:
        return 0, 0

    ordered_dates = sorted(contributions)

    longest_streak = 0
    running_streak = 0

    for current_date in ordered_dates:
        if contributions[current_date] > 0:
            running_streak += 1
            longest_streak = max(longest_streak, running_streak)
        else:
            running_streak = 0

    today = datetime.now(timezone.utc).date()

    # If today has no contribution yet, calculate from yesterday.
    cursor = today
    if contributions.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)

    current_streak = 0

    while contributions.get(cursor, 0) > 0:
        current_streak += 1
        cursor -= timedelta(days=1)

    return current_streak, longest_streak


def collect_language_data(
    repositories: list[dict[str, Any]],
) -> list[tuple[str, int, str]]:
    totals: Counter[str] = Counter()
    colors: dict[str, str] = {}

    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            language = edge["node"]["name"]
            size = int(edge["size"])
            color = edge["node"].get("color") or "#8B949E"

            totals[language] += size
            colors[language] = color

    return [
        (name, size, colors[name])
        for name, size in totals.most_common(5)
    ]


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def build_language_section(
    languages: list[tuple[str, int, str]],
) -> str:
    if not languages:
        return """
        <text x="0" y="50" class="muted">
          Languages will appear after repositories contain detectable code.
        </text>
        """

    total_size = sum(size for _, size, _ in languages)
    bar_width = 378
    bar_x = 0

    bar_parts: list[str] = []
    legend_parts: list[str] = []

    for index, (name, size, color) in enumerate(languages):
        percentage = (size / total_size) * 100
        segment_width = max((size / total_size) * bar_width, 2)

        bar_parts.append(
            f'<rect x="{bar_x:.2f}" y="50" '
            f'width="{segment_width:.2f}" height="12" '
            f'fill="{escape(color)}" />'
        )

        legend_y = 90 + index * 24

        legend_parts.append(
            f"""
            <circle cx="5" cy="{legend_y - 4}" r="5"
                    fill="{escape(color)}" />
            <text x="18" y="{legend_y}" class="label">
              {escape(name)}
            </text>
            <text x="378" y="{legend_y}" text-anchor="end"
                  class="value">
              {percentage:.1f}%
            </text>
            """
        )

        bar_x += segment_width

    return "\n".join(bar_parts + legend_parts)


def generate_svg(user: dict[str, Any]) -> str:
    repositories_data = user["repositories"]
    repositories = repositories_data["nodes"]

    repo_count = repositories_data["totalCount"]
    followers = user["followers"]["totalCount"]
    stars = sum(repository["stargazerCount"] for repository in repositories)

    calendar = user["contributionsCollection"]["contributionCalendar"]
    total_contributions = calendar["totalContributions"]

    contribution_days = [
        day
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]

    current_streak, longest_streak = calculate_streaks(contribution_days)
    languages = collect_language_data(repositories)
    language_section = build_language_section(languages)

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="900"
     height="390"
     viewBox="0 0 900 390"
     role="img"
     aria-labelledby="title description">

  <title id="title">{escape(USERNAME)} GitHub activity</title>

  <desc id="description">
    Automatically updated GitHub statistics and language usage.
  </desc>

  <defs>
    <linearGradient id="blue-line" x1="0" x2="1">
      <stop offset="0%" stop-color="#58A6FF" stop-opacity="0.15"/>
      <stop offset="50%" stop-color="#58A6FF"/>
      <stop offset="100%" stop-color="#58A6FF" stop-opacity="0.15"/>
    </linearGradient>
  </defs>

  <style>
    .title {{
      font: 700 24px -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
      fill: #58A6FF;
    }}

    .section {{
      font: 700 18px -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
      fill: #58A6FF;
    }}

    .label {{
      font: 500 14px -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
      fill: #C9D1D9;
    }}

    .value {{
      font: 700 16px -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
      fill: #F0F6FC;
    }}

    .big {{
      font: 700 28px -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
      fill: #58A6FF;
    }}

    .muted {{
      font: 400 12px -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
      fill: #8B949E;
    }}
  </style>

  <rect x="1"
        y="1"
        width="898"
        height="388"
        rx="18"
        fill="none"
        stroke="#30363D"/>

  <text x="36" y="42" class="title">GitHub Activity</text>

  <rect x="36"
        y="57"
        width="828"
        height="2"
        rx="1"
        fill="url(#blue-line)"/>

  <!-- GitHub statistics -->

  <g transform="translate(36,88)">
    <text x="0" y="0" class="section">GitHub Stats</text>

    <circle cx="8" cy="38" r="4" fill="#58A6FF"/>
    <text x="24" y="43" class="label">Public repositories</text>
    <text x="330" y="43" text-anchor="end" class="value">
      {repo_count}
    </text>

    <circle cx="8" cy="72" r="4" fill="#58A6FF"/>
    <text x="24" y="77" class="label">Contributions</text>
    <text x="330" y="77" text-anchor="end" class="value">
      {total_contributions}
    </text>

    <circle cx="8" cy="106" r="4" fill="#58A6FF"/>
    <text x="24" y="111" class="label">Total stars earned</text>
    <text x="330" y="111" text-anchor="end" class="value">
      {stars}
    </text>

    <circle cx="8" cy="140" r="4" fill="#58A6FF"/>
    <text x="24" y="145" class="label">Followers</text>
    <text x="330" y="145" text-anchor="end" class="value">
      {followers}
    </text>
  </g>

  <line x1="450"
        y1="88"
        x2="450"
        y2="258"
        stroke="#30363D"/>

  <!-- Languages -->

  <g transform="translate(486,88)">
    <text x="0" y="0" class="section">Most Used Languages</text>

    <rect x="0"
          y="50"
          width="378"
          height="12"
          rx="6"
          fill="#21262D"/>

    {language_section}
  </g>

  <line x1="36"
        y1="280"
        x2="864"
        y2="280"
        stroke="#30363D"/>

  <!-- Bottom metrics -->

  <g transform="translate(0,300)">
    <line x1="300"
          y1="0"
          x2="300"
          y2="58"
          stroke="#30363D"/>

    <line x1="600"
          y1="0"
          x2="600"
          y2="58"
          stroke="#30363D"/>

    <text x="150" y="25" text-anchor="middle" class="big">
      {total_contributions}
    </text>

    <text x="150" y="48" text-anchor="middle" class="muted">
      Total contributions
    </text>

    <circle cx="450"
            cy="20"
            r="27"
            fill="none"
            stroke="#30363D"
            stroke-width="5"/>

    <circle cx="450"
            cy="20"
            r="27"
            fill="none"
            stroke="#58A6FF"
            stroke-width="5"
            stroke-linecap="round"
            stroke-dasharray="110 60"
            transform="rotate(-90 450 20)"/>

    <text x="450" y="27" text-anchor="middle" class="big">
      {current_streak}
    </text>

    <text x="450" y="48" text-anchor="middle" class="muted">
      Current streak
    </text>

    <text x="750" y="25" text-anchor="middle" class="big">
      {longest_streak}
    </text>

    <text x="750" y="48" text-anchor="middle" class="muted">
      Longest streak
    </text>
  </g>

  <text x="864"
        y="378"
        text-anchor="end"
        class="muted">
    Updated {escape(updated_at)}
  </text>
</svg>
"""


def main() -> int:
    try:
        user = graphql_request()
        svg = generate_svg(user)

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(svg, encoding="utf-8")

        print(f"Updated {OUTPUT_PATH}")
        return 0

    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
