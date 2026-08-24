from __future__ import annotations

import base64
import html
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

ICONS_DIR = ROOT / "assets" / "learning" / "icons"
OUTPUT_DIR = ROOT / "assets" / "learning"


BLUE = "#58A6FF"
WHITE = "#F0F6FC"
MUTED = "#8B949E"
LINE = "#21262D"

WIDTH = 180
HEIGHT = 78


PLATFORMS = [
    {
        "slug": "bootdev",
        "title": "Boot.dev",
        "description": "Backend Path",
        "status": "In Progress",
        "icon": ICONS_DIR / "bootdev.png",
        "icon_width": 24,
        "icon_height": 24,
        "icon_y": 0,
        "separator": True,
    },
    {
        "slug": "labex",
        "title": "LabEx",
        "description": "Linux Skills",
        "status": "In Progress",
        "icon": ICONS_DIR / "labex.jpg",
        "icon_width": 21,
        "icon_height": 21,
        "icon_y": 1,
        "separator": True,
    },
    {
        "slug": "kodekloud",
        "title": "KodeKloud",
        "description": "DevOps / Cloud",
        "status": "Planned",
        "icon": ICONS_DIR / "kodekloud.png",
        "icon_width": 46,
        "icon_height": 30,
        "icon_y": 0,
        "separator": True,
    },
    {
        "slug": "tryhackme",
        "title": "TryHackMe",
        "description": "Security",
        "status": "Planned",
        "icon": ICONS_DIR / "tryhackme.png",
        "icon_width": 31,
        "icon_height": 28,
        "icon_y": 0,
        "separator": False,
    },
]


def image_to_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    if suffix not in mime_types:
        raise ValueError(f"Unsupported image type: {path}")

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")

    return f"data:{mime_types[suffix]};base64,{encoded}"


def build_widget(platform: dict) -> str:
    icon_uri = image_to_data_uri(platform["icon"])

    title = html.escape(platform["title"])
    description = html.escape(platform["description"])
    status = html.escape(platform["status"])

    icon_width = platform["icon_width"]
    icon_height = platform["icon_height"]
    icon_y = platform["icon_y"]

    icon_x = (WIDTH - icon_width) / 2

    vertical_separator = ""

    if platform["separator"]:
        vertical_separator = f"""
  <line
    x1="{WIDTH - 1}"
    y1="3"
    x2="{WIDTH - 1}"
    y2="66"
    stroke="{LINE}"
    stroke-width="1"
  />
"""

    return f"""<svg
  xmlns="http://www.w3.org/2000/svg"
  width="{WIDTH}"
  height="{HEIGHT}"
  viewBox="0 0 {WIDTH} {HEIGHT}"
  role="img"
  aria-label="{title} learning progress"
>
  <style>
    .title {{
      fill: {BLUE};
      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Helvetica,
        Arial,
        sans-serif;
      font-size: 13px;
      font-weight: 600;
    }}

    .description {{
      fill: {WHITE};
      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Helvetica,
        Arial,
        sans-serif;
      font-size: 11px;
      font-weight: 500;
    }}

    .status {{
      fill: {MUTED};
      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Helvetica,
        Arial,
        sans-serif;
      font-size: 9px;
      font-weight: 400;
    }}
  </style>

  <image
    href="{icon_uri}"
    x="{icon_x}"
    y="{icon_y}"
    width="{icon_width}"
    height="{icon_height}"
    preserveAspectRatio="xMidYMid meet"
  />

  <text
    x="90"
    y="35"
    text-anchor="middle"
    class="title"
  >{title}</text>

  <text
    x="90"
    y="51"
    text-anchor="middle"
    class="description"
  >{description}</text>

  <text
    x="90"
    y="64"
    text-anchor="middle"
    class="status"
  >{status}</text>

  <line
    x1="28"
    y1="73"
    x2="152"
    y2="73"
    stroke="{LINE}"
    stroke-width="1"
  />

{vertical_separator}
</svg>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for platform in PLATFORMS:
        output_path = OUTPUT_DIR / f"{platform['slug']}.svg"

        svg = build_widget(platform)

        output_path.write_text(svg, encoding="utf-8")

        print(f"Generated: {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()