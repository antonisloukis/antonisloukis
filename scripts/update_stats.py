import os
import json
import urllib.request
from datetime import datetime

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME", "antonisloukis")

OUTPUT_PATH = "assets/github-activity.svg"

BG = "#0d1117"
BLUE = "#58a6ff"
WHITE = "#e6edf3"
MUTED = "#8b949e"
LINE = "#21262d"


def graphql_query(query, variables=None):
    data = json.dumps({
        "query": query,
        "variables": variables or {}
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=data,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USERNAME,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))

    if "errors" in result:
        raise Exception(result["errors"])

    return result["data"]


def rest_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USERNAME,
        },
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def get_profile_data():
    query = """
    query($login: String!) {
      user(login: $login) {
        followers {
          totalCount
        }
        repositories(ownerAffiliations: OWNER, isFork: false, first: 100, privacy: PUBLIC) {
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
          }
          totalPullRequestContributions
          totalIssueContributions
          totalCommitContributions
        }
      }
    }
    """

    data = graphql_query(query, {"login": USERNAME})
    user = data["user"]

    repos = user["repositories"]["nodes"]
    public_repos = user["repositories"]["totalCount"]
    followers = user["followers"]["totalCount"]

    total_stars = sum(repo["stargazerCount"] for repo in repos)

    contributions = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    total_prs = user["contributionsCollection"]["totalPullRequestContributions"]
    total_issues = user["contributionsCollection"]["totalIssueContributions"]
    total_commits = user["contributionsCollection"]["totalCommitContributions"]

    language_sizes = {}
language_colors = {}

for repo in repos:
    for edge in repo["languages"]["edges"]:
        name = edge["node"]["name"]
        size = edge["size"]
        color = edge["node"].get("color") or BLUE

        language_sizes[name] = language_sizes.get(name, 0) + size
        language_colors[name] = color

total_language_size = sum(language_sizes.values()) or 1

languages = []

for name, size in sorted(
    language_sizes.items(),
    key=lambda item: item[1],
    reverse=True,
)[:6]:
    percentage = round(
        (size / total_language_size) * 100,
        1,
    )

    languages.append(
        (
            name,
            percentage,
            language_colors[name],
        )
    )

    return {
        "public_repos": public_repos,
        "followers": followers,
        "total_stars": total_stars,
        "total_commits": total_commits,
        "total_prs": total_prs,
        "total_issues": total_issues,
        "contributed_this_year": contributions,
        "languages": languages,
    }


def get_longest_streak_and_current_streak():
    # Using GitHub contributions GraphQL via contribution calendar weeks
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
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

    data = graphql_query(query, {"login": USERNAME})
    weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]

    days = []
    for week in weeks:
        for day in week["contributionDays"]:
            days.append(day)

    days.sort(key=lambda d: d["date"])

    longest = 0
    current = 0
    temp = 0

    for day in days:
        if day["contributionCount"] > 0:
            temp += 1
            longest = max(longest, temp)
        else:
            temp = 0

    for day in reversed(days):
        if day["contributionCount"] > 0:
            current += 1
        else:
            break

    return current, longest


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def icon_star(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <path d="M12 2.5l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 16.8 6.4 19.7l1.1-6.2L3 9.1l6.2-.9L12 2.5z"
            fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round"/>
    </g>
    '''


def icon_commit(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <path d="M12 4a8 8 0 1 1-5.7 2.3" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
      <path d="M4.2 3.8H8v3.8" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </g>
    '''


def icon_pr(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <circle cx="7" cy="5" r="2" fill="none" stroke="{color}" stroke-width="1.8"/>
      <circle cx="17" cy="19" r="2" fill="none" stroke="{color}" stroke-width="1.8"/>
      <circle cx="17" cy="5" r="2" fill="none" stroke="{color}" stroke-width="1.8"/>
      <path d="M7 7v10a2 2 0 0 0 2 2h6" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
      <path d="M15 5h-4a2 2 0 0 0-2 2v2" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
    </g>
    '''


def icon_issue(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <circle cx="12" cy="12" r="8" fill="none" stroke="{color}" stroke-width="1.8"/>
      <path d="M12 7.5v5" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
      <circle cx="12" cy="15.8" r="1" fill="{color}"/>
    </g>
    '''


def icon_calendar(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <rect x="4" y="6" width="16" height="14" rx="1.8" fill="none" stroke="{color}" stroke-width="1.8"/>
      <path d="M4 10h16" stroke="{color}" stroke-width="1.8"/>
      <path d="M8 3.8v4M16 3.8v4" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
    </g>
    '''


def icon_people(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <circle cx="9" cy="9" r="2.3" fill="none" stroke="{color}" stroke-width="1.6"/>
      <circle cx="15" cy="9" r="2.3" fill="none" stroke="{color}" stroke-width="1.6"/>
      <path d="M5.5 18c.8-2.6 2.6-4 5.5-4s4.7 1.4 5.5 4" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>
      <path d="M2.8 18c.6-1.8 1.7-2.8 3.2-3.3M21.2 18c-.6-1.8-1.7-2.8-3.2-3.3" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>
    </g>
    '''


def icon_flame(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <path d="M12 3.5c1.5 2.3 3.8 4 3.8 7.1A3.8 3.8 0 1 1 8.2 11c0-1.9 1-3.4 2.4-4.8.2 1.6.9 2.7 1.4 3.2.8-1.1 1-2.7 0-5.9z"
            fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round"/>
    </g>
    '''


def icon_trophy(x, y, color):
    return f'''
    <g transform="translate({x},{y}) scale(0.95)">
      <path d="M8 5h8v3a4 4 0 0 1-8 0V5z" fill="none" stroke="{color}" stroke-width="1.8"/>
      <path d="M6 6H4a2 2 0 0 0 2 3M18 6h2a2 2 0 0 1-2 3" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
      <path d="M12 12v4M9 20h6" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
    </g>
    '''


def build_svg(stats, current_streak, longest_streak):
    width = 1000
    height = 460

    x0 = 28
    left_w = 460
    right_x = 520
    right_w = 452

    lang_title_y = 88
    list_start_y = 128
    row_gap = 42

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    language_bar_y = 170
    language_bar_x = right_x + 24
    language_bar_w = 360
    language_bar_h = 8

    languages = stats["languages"][:6]

if not languages:
    languages = [
        ("No data", 100.0, MUTED)
    ]

language_segments = []
language_legend = []

segment_cursor = language_bar_x

for index, (name, percentage, color) in enumerate(languages):
    if index == len(languages) - 1:
        segment_width = (
            language_bar_x
            + language_bar_w
            - segment_cursor
        )
    else:
        segment_width = (
            language_bar_w
            * percentage
            / 100
        )

    language_segments.append(
        f'''
        <rect
          x="{segment_cursor:.2f}"
          y="{language_bar_y}"
          width="{max(segment_width, 1.5):.2f}"
          height="{language_bar_h}"
          fill="{color}"
        />
        '''
    )

    segment_cursor += segment_width

    column = index % 2
    row = index // 2

    legend_x = (
        language_bar_x
        + column * 190
    )

    legend_y = (
        language_bar_y
        + 34
        + row * 30
    )

    percentage_x = (
        legend_x
        + 165
    )

    language_legend.append(
        f'''
        <circle
          cx="{legend_x + 5}"
          cy="{legend_y - 5}"
          r="4.5"
          fill="{color}"
        />

        <text
          x="{legend_x + 17}"
          y="{legend_y}"
          fill="{WHITE}"
          font-family="Segoe UI, Arial, sans-serif"
          font-size="17"
          font-weight="700">
          {esc(name)}
        </text>

        <text
          x="{percentage_x}"
          y="{legend_y}"
          text-anchor="end"
          fill="{WHITE}"
          font-family="Segoe UI, Arial, sans-serif"
          font-size="16"
          font-weight="700">
          {percentage:.1f}%
        </text>
        '''
    )

language_segments_svg = "\n".join(
    language_segments
)

language_legend_svg = "\n".join(
    language_legend
)

    total_commits = stats["total_commits"]
    total_prs = stats["total_prs"]
    total_issues = stats["total_issues"]
    total_stars = stats["total_stars"]
    contributed_this_year = stats["contributed_this_year"]

    svg = f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" rx="16" fill="{BG}"/>

  <!-- Section title -->
  <text x="0" y="0" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="700" visibility="hidden">Development Metrics</text>

  <!-- Vertical divider -->
  <line x1="500" y1="70" x2="500" y2="285" stroke="{LINE}" stroke-width="2"/>

  <!-- GitHub Stats title -->
  <text x="{x0}" y="60" fill="{BLUE}" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700">GitHub Stats</text>

  <!-- Most Used Languages title -->
  <text x="{right_x + 24}" y="{lang_title_y}" fill="{BLUE}" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700">Most Used Languages</text>

  <!-- Stats list -->
  {icon_star(x0, list_start_y - 18, BLUE)}
  <text x="{x0 + 36}" y="{list_start_y}" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">Total Stars Earned:</text>
  <text x="{left_w - 10}" y="{list_start_y}" text-anchor="end" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">{total_stars}</text>

  {icon_commit(x0, list_start_y + row_gap - 18, BLUE)}
  <text x="{x0 + 36}" y="{list_start_y + row_gap}" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">Total Commits:</text>
  <text x="{left_w - 10}" y="{list_start_y + row_gap}" text-anchor="end" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">{total_commits}</text>

  {icon_pr(x0, list_start_y + row_gap*2 - 18, BLUE)}
  <text x="{x0 + 36}" y="{list_start_y + row_gap*2}" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">Total PRs:</text>
  <text x="{left_w - 10}" y="{list_start_y + row_gap*2}" text-anchor="end" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">{total_prs}</text>

  {icon_issue(x0, list_start_y + row_gap*3 - 18, BLUE)}
  <text x="{x0 + 36}" y="{list_start_y + row_gap*3}" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">Total Issues:</text>
  <text x="{left_w - 10}" y="{list_start_y + row_gap*3}" text-anchor="end" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">{total_issues}</text>

  {icon_calendar(x0, list_start_y + row_gap*4 - 18, BLUE)}
  <text x="{x0 + 36}" y="{list_start_y + row_gap*4}" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">Contributed this year:</text>
  <text x="{left_w - 10}" y="{list_start_y + row_gap*4}" text-anchor="end" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">{contributed_this_year}</text>

  <!-- Languages -->
  <!-- Rounded segmented language bar -->

<defs>
  <clipPath id="language-bar-clip">
    <rect
      x="{language_bar_x}"
      y="{language_bar_y}"
      width="{language_bar_w}"
      height="{language_bar_h}"
      rx="{language_bar_h / 2}"
    />
  </clipPath>
</defs>

<rect
  x="{language_bar_x}"
  y="{language_bar_y}"
  width="{language_bar_w}"
  height="{language_bar_h}"
  rx="{language_bar_h / 2}"
  fill="#161b22"
/>

<g clip-path="url(#language-bar-clip)">
  {language_segments_svg}
</g>

<!-- Language legend -->

{language_legend_svg}

  <!-- Bottom metrics -->
  <line x1="28" y1="332" x2="972" y2="332" stroke="{LINE}" stroke-width="2"/>
  <line x1="333" y1="352" x2="333" y2="432" stroke="{LINE}" stroke-width="2"/>
  <line x1="667" y1="352" x2="667" y2="432" stroke="{LINE}" stroke-width="2"/>

  {icon_people(150, 352, BLUE)}
  <text x="166" y="410" text-anchor="middle" fill="{BLUE}" font-family="Segoe UI, Arial, sans-serif" font-size="42" font-weight="800">{contributed_this_year}</text>
  <text x="166" y="438" text-anchor="middle" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="600">Total contributions</text>

  {icon_flame(484, 352, BLUE)}
  <text x="500" y="410" text-anchor="middle" fill="{BLUE}" font-family="Segoe UI, Arial, sans-serif" font-size="42" font-weight="800">{current_streak}</text>
  <text x="500" y="438" text-anchor="middle" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="600">Current streak</text>

  {icon_trophy(818, 352, BLUE)}
  <text x="834" y="410" text-anchor="middle" fill="{BLUE}" font-family="Segoe UI, Arial, sans-serif" font-size="42" font-weight="800">{longest_streak}</text>
  <text x="834" y="438" text-anchor="middle" fill="{WHITE}" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="600">Longest streak</text>

  <text x="952" y="438" text-anchor="end" fill="{MUTED}" font-family="Segoe UI, Arial, sans-serif" font-size="14">Updated {updated}</text>
</svg>'''
    return svg


def main():
    if not GITHUB_TOKEN:
        raise Exception("GITHUB_TOKEN is not set")

    stats = get_profile_data()
    current_streak, longest_streak = get_longest_streak_and_current_streak()

    svg = build_svg(stats, current_streak, longest_streak)

    os.makedirs("assets", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
