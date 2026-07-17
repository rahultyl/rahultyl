#!/usr/bin/env python3
"""Generate self-hosted GitHub stat cards (tokyonight theme) as SVGs.

Uses only the REST API and the public contributions page — the Actions
GITHUB_TOKEN erratically rejects GraphQL contributionsCollection queries
with RESOURCE_LIMITS_EXCEEDED, so GraphQL is avoided entirely.
Writes assets/stats.svg and assets/langs.svg.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "")
USER = os.environ.get("USERNAME", "rahultyl")

BG = "#1a1b27"
TITLE = "#70a5fd"
TEXT = "#a9b1d6"
ICON = "#bf91f3"
VALUE = "#d6e4fd"
TRACK = "#2b2d42"
FONT = "'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"

LANG_COLORS = {
    "Python": "#3572A5", "HTML": "#e34c26", "CSS": "#663399", "Shell": "#89e051",
    "Dockerfile": "#384d54", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "C": "#555555", "C++": "#f34b7d", "Jupyter Notebook": "#DA5B0B",
    "Makefile": "#427819", "Go": "#00ADD8", "Rust": "#dea584", "Java": "#b07219",
}


def get(url, auth=True):
    headers = {"User-Agent": USER}
    if "api.github.com" in url:
        headers["Accept"] = "application/vnd.github+json"
        if TOKEN and auth:
            headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
    return json.loads(body) if "api.github.com" in url else body


def search(url):
    """The Actions app token silently returns empty search results;
    retry without auth before trusting a zero."""
    data = get(url)
    if not data.get("total_count"):
        try:
            data = get(url, auth=False)
        except urllib.error.HTTPError:
            pass
    return data


def collect():
    profile = get(f"https://api.github.com/users/{USER}")
    repos = get(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")

    # Total contributions from the public contributions page (this also
    # reflects the "include private contributions" profile setting).
    page = get(f"https://github.com/users/{USER}/contributions")
    m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", page)
    total = int(m.group(1).replace(",", "")) if m else 0

    since = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    commit_search = search(
        f"https://api.github.com/search/commits?q=author:{USER}+author-date:%3E{since}&per_page=100"
    )
    commits = commit_search.get("total_count", 0)
    contributed = len({item["repository"]["full_name"] for item in commit_search.get("items", [])})
    prs = search(f"https://api.github.com/search/issues?q=author:{USER}+type:pr").get("total_count", 0)
    issues = search(f"https://api.github.com/search/issues?q=author:{USER}+type:issue").get("total_count", 0)

    if total and not (commits or prs):
        raise SystemExit("search results look degraded; refusing to write stale-worse cards")

    sizes, names = {}, [r for r in repos if not r["fork"]] or repos
    for repo in names:
        for lang, size in get(f"https://api.github.com/repos/{repo['full_name']}/languages").items():
            sizes[lang] = sizes.get(lang, 0) + size
    langs = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]

    return {
        "name": profile.get("name") or USER,
        "stars": sum(r["stargazers_count"] for r in repos),
        "total": total,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "contributed": max(contributed, 1),
        "langs": langs,
    }


def fmt(n):
    return f"{n:,}"


def stats_card(d):
    rows = [
        ("★", "Total Stars Earned", d["stars"]),
        ("⏱", "Commits (last year)", d["commits"]),
        ("⇄", "Pull Requests", d["prs"]),
        ("◉", "Issues", d["issues"]),
        ("◫", "Contributed to", d["contributed"]),
    ]
    row_svg = ""
    for i, (icon, label, val) in enumerate(rows):
        y = 70 + i * 26
        row_svg += (
            f'<text x="25" y="{y}" fill="{ICON}" font-size="14">{icon}</text>'
            f'<text x="50" y="{y}" fill="{TEXT}" font-size="14">{label}:</text>'
            f'<text x="250" y="{y}" fill="{VALUE}" font-size="14" font-weight="600" text-anchor="end">{fmt(val)}</text>'
        )
    circumference = 2 * 3.14159 * 40
    dash = circumference * 0.72
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="450" height="205" viewBox="0 0 450 205" role="img" aria-label="GitHub stats">
  <rect width="450" height="205" rx="6" fill="{BG}"/>
  <g font-family="{FONT}">
    <text x="25" y="38" fill="{TITLE}" font-size="17" font-weight="700">{d["name"]}&#8217;s GitHub Stats</text>
    {row_svg}
    <circle cx="360" cy="125" r="40" fill="none" stroke="{TRACK}" stroke-width="7"/>
    <circle cx="360" cy="125" r="40" fill="none" stroke="{ICON}" stroke-width="7"
      stroke-linecap="round" stroke-dasharray="{dash:.1f} {circumference:.1f}"
      transform="rotate(-90 360 125)"/>
    <text x="360" y="122" fill="{VALUE}" font-size="20" font-weight="700" text-anchor="middle">{fmt(d["total"])}</text>
    <text x="360" y="140" fill="{TEXT}" font-size="10" text-anchor="middle">contributions</text>
    <text x="360" y="152" fill="{TEXT}" font-size="10" text-anchor="middle">last year</text>
  </g>
</svg>
"""


def langs_card(d):
    top = d["langs"]
    total = sum(v for _, v in top) or 1

    bar_x, bar_w = 25, 270
    x = bar_x
    bar_svg = f'<clipPath id="bar"><rect x="{bar_x}" y="55" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">'
    for name, size in top:
        color = LANG_COLORS.get(name, "#8b949e")
        w = bar_w * size / total
        bar_svg += f'<rect x="{x:.1f}" y="55" width="{w + 1:.1f}" height="10" fill="{color}"/>'
        x += w
    bar_svg += "</g>"

    legend = ""
    for i, (name, size) in enumerate(top):
        color = LANG_COLORS.get(name, "#8b949e")
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 140, 92 + row * 24
        pct = 100 * size / total
        legend += (
            f'<circle cx="{lx}" cy="{ly - 4}" r="5" fill="{color}"/>'
            f'<text x="{lx + 12}" y="{ly}" fill="{TEXT}" font-size="12">{name} '
            f'<tspan fill="{VALUE}" font-weight="600">{pct:.1f}%</tspan></text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="205" viewBox="0 0 320 205" role="img" aria-label="Most used languages">
  <rect width="320" height="205" rx="6" fill="{BG}"/>
  <g font-family="{FONT}">
    <text x="25" y="38" fill="{TITLE}" font-size="17" font-weight="700">Most Used Languages</text>
    {bar_svg}
    {legend}
  </g>
</svg>
"""


def main():
    data = collect()
    os.makedirs("assets", exist_ok=True)
    with open("assets/stats.svg", "w") as f:
        f.write(stats_card(data))
    with open("assets/langs.svg", "w") as f:
        f.write(langs_card(data))
    print(f"wrote cards: {json.dumps({k: v for k, v in data.items() if k != 'langs'})}")


if __name__ == "__main__":
    main()
