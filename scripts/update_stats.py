#!/usr/bin/env python3
"""Regenerate assets/stats-{dark,light}.svg from live GitHub data.

Stdlib only. Auth via the GITHUB_TOKEN environment variable.
Language shares are byte shares averaged per repository (equal weight per
repo), so one large team codebase cannot dominate the distribution.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

LOGIN = "Ilyes-Jamoussi"
API = "https://api.github.com"
TOP_N = 5
ASSETS = Path(__file__).resolve().parent.parent / "assets"

PALETTES = {
    "dark": {
        "bg_top": "#0d1117", "bg_bottom": "#161b22", "border": "#30363d",
        "heading": "#f0f6fc", "label": "#8b949e", "faint": "#6e7681",
        "accent": "#2f81f7", "accent2": "#39c5cf", "track": "#21262d",
    },
    "light": {
        "bg_top": "#ffffff", "bg_bottom": "#f6f8fa", "border": "#d0d7de",
        "heading": "#1f2328", "label": "#57606a", "faint": "#6e7681",
        "accent": "#0969da", "accent2": "#218bff", "track": "#eaeef2",
    },
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"


def api_get(path: str) -> object:
    req = urllib.request.Request(API + path)
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def graphql(query: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("GITHUB_TOKEN is required for the GraphQL contributions query")
    req = urllib.request.Request(
        API + "/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def collect() -> tuple[int, int, list[tuple[str, float]]]:
    repos = [
        r for r in api_get(f"/users/{LOGIN}/repos?per_page=100&type=owner")
        if not r["fork"]
    ]
    shares: dict[str, float] = {}
    counted = 0
    for repo in repos:
        langs = api_get(f"/repos/{LOGIN}/{repo['name']}/languages")
        total = sum(langs.values())
        if not total:
            continue
        counted += 1
        for lang, size in langs.items():
            shares[lang] = shares.get(lang, 0.0) + size / total
    averaged = sorted(
        ((lang, 100.0 * acc / counted) for lang, acc in shares.items()),
        key=lambda kv: -kv[1],
    )[:TOP_N]

    data = graphql(
        f'{{ user(login: "{LOGIN}") {{ contributionsCollection '
        f"{{ contributionCalendar {{ totalContributions }} }} }} }}"
    )
    contributions = data["data"]["user"]["contributionsCollection"][
        "contributionCalendar"]["totalContributions"]
    return contributions, len(repos), averaged


def render(theme: str, contributions: int, repo_count: int,
           langs: list[tuple[str, float]]) -> str:
    p = PALETTES[theme]
    max_share = max(share for _, share in langs)
    rows = []
    for i, (lang, share) in enumerate(langs):
        y = 92 + i * 27
        bar_w = round(400 * share / max_share, 1)
        rows.append(f"""
  <text x="540" y="{y + 8}" class="lang">{lang}</text>
  <rect x="680" y="{y}" width="400" height="8" rx="4" fill="{p['track']}"/>
  <rect x="680" y="{y}" width="{bar_w}" height="8" rx="4" fill="{p['accent']}" class="bar" style="animation-delay: {0.1 * i:.1f}s"/>
  <text x="1136" y="{y + 8}" text-anchor="end" class="pct">{share:.1f}%</text>""")
    return f"""<svg width="1200" height="250" viewBox="0 0 1200 250" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="statsTitle">
  <title id="statsTitle">GitHub activity: {contributions} contributions in the last 12 months, {repo_count} public repositories, most used languages</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{p['bg_top']}"/>
      <stop offset="1" stop-color="{p['bg_bottom']}"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{p['accent']}"/>
      <stop offset="1" stop-color="{p['accent2']}"/>
    </linearGradient>
  </defs>
  <style>
    text {{ font-family: {FONT}; }}
    .caps {{ font-size: 13px; font-weight: 600; letter-spacing: 2px; fill: {p['label']}; }}
    .big {{ font-size: 64px; font-weight: 700; letter-spacing: -1px; fill: {p['heading']}; }}
    .sub {{ font-size: 16px; fill: {p['label']}; }}
    .lang {{ font-size: 14px; fill: {p['heading']}; }}
    .pct {{ font-size: 13px; fill: {p['label']}; }}
    .note {{ font-size: 11px; fill: {p['faint']}; }}
    .bar {{ transform-origin: 680px 0; animation: grow 0.8s ease-out backwards; }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    @media (prefers-reduced-motion: reduce) {{ .bar {{ animation: none; }} }}
  </style>
  <rect x="0.5" y="0.5" width="1199" height="249" rx="14" fill="url(#bg)" stroke="{p['border']}"/>
  <text x="64" y="66" class="caps">CONTRIBUTIONS · LAST 12 MONTHS</text>
  <text x="64" y="146" class="big">{contributions}</text>
  <rect x="66" y="164" width="72" height="4" rx="2" fill="url(#accent)"/>
  <text x="64" y="200" class="sub">{repo_count} public repositories</text>
  <line x1="480" y1="48" x2="480" y2="202" stroke="{p['border']}"/>
  <text x="540" y="66" class="caps">MOST USED LANGUAGES</text>{''.join(rows)}
  <text x="1136" y="232" text-anchor="end" class="note">byte share averaged across public repositories · refreshed weekly</text>
</svg>
"""


def main() -> None:
    contributions, repo_count, langs = collect()
    ASSETS.mkdir(exist_ok=True)
    for theme in ("dark", "light"):
        out = ASSETS / f"stats-{theme}.svg"
        out.write_text(render(theme, contributions, repo_count, langs))
        print(f"wrote {out}")
    print(f"contributions={contributions} repos={repo_count} langs={langs}")


if __name__ == "__main__":
    main()
