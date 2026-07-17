#!/usr/bin/env python3
"""Generate self-hosted GitHub stat cards (tokyonight theme) as SVGs.

Runs in GitHub Actions with the default GITHUB_TOKEN; queries the GraphQL
API for public stats and writes assets/stats.svg and assets/langs.svg.
"""
import json
import os
import urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
USER = os.environ.get("USERNAME", "rahultyl")

BG = "#1a1b27"
TITLE = "#70a5fd"
TEXT = "#a9b1d6"
ICON = "#bf91f3"
VALUE = "#d6e4fd"
TRACK = "#2b2d42"
FONT = "'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar { totalContributions }
    }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) {
      totalCount
    }
    repositories(first: 100, ownerAffiliations: OWNER) {
      nodes {
        stargazerCount
        isFork
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL errors: {data['errors']}")
    return data["data"]


def fmt(n):
    return f"{n:,}"


def stats_card(user):
    cc = user["contributionsCollection"]
    commits = cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    total = cc["contributionCalendar"]["totalContributions"]
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    rows = [
        ("★", "Total Stars Earned", stars),
        ("⏱", "Commits (last year)", commits),
        ("⇄", "Pull Requests", cc["totalPullRequestContributions"]),
        ("◉", "Issues", cc["totalIssueContributions"]),
        ("◫", "Contributed to", user["repositoriesContributedTo"]["totalCount"]),
    ]
    row_svg = ""
    for i, (icon, label, val) in enumerate(rows):
        y = 70 + i * 26
        row_svg += (
            f'<text x="25" y="{y}" fill="{ICON}" font-size="14">{icon}</text>'
            f'<text x="50" y="{y}" fill="{TEXT}" font-size="14">{label}:</text>'
            f'<text x="250" y="{y}" fill="{VALUE}" font-size="14" font-weight="600" text-anchor="end">{fmt(val)}</text>'
        )
    # contributions ring on the right
    circumference = 2 * 3.14159 * 40
    dash = circumference * 0.72
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="450" height="205" viewBox="0 0 450 205" role="img" aria-label="GitHub stats">
  <rect width="450" height="205" rx="6" fill="{BG}"/>
  <g font-family="{FONT}">
    <text x="25" y="38" fill="{TITLE}" font-size="17" font-weight="700">{user["name"] or USER}&#8217;s GitHub Stats</text>
    {row_svg}
    <circle cx="360" cy="125" r="40" fill="none" stroke="{TRACK}" stroke-width="7"/>
    <circle cx="360" cy="125" r="40" fill="none" stroke="{ICON}" stroke-width="7"
      stroke-linecap="round" stroke-dasharray="{dash:.1f} {circumference:.1f}"
      transform="rotate(-90 360 125)"/>
    <text x="360" y="122" fill="{VALUE}" font-size="20" font-weight="700" text-anchor="middle">{fmt(total)}</text>
    <text x="360" y="140" fill="{TEXT}" font-size="10" text-anchor="middle">contributions</text>
    <text x="360" y="152" fill="{TEXT}" font-size="10" text-anchor="middle">last year</text>
  </g>
</svg>
"""


def langs_card(user):
    sizes = {}
    colors = {}
    repos = [r for r in user["repositories"]["nodes"] if not r["isFork"]]
    if not any(r["languages"]["edges"] for r in repos):
        repos = user["repositories"]["nodes"]  # fall back to including forks
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#8b949e"
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    total = sum(v for _, v in top) or 1

    bar_x, bar_w = 25, 270
    x = bar_x
    bar_svg = f'<clipPath id="bar"><rect x="{bar_x}" y="55" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">'
    for name, size in top:
        w = bar_w * size / total
        bar_svg += f'<rect x="{x:.1f}" y="55" width="{w + 1:.1f}" height="10" fill="{colors[name]}"/>'
        x += w
    bar_svg += "</g>"

    legend = ""
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 140, 92 + row * 24
        pct = 100 * size / total
        legend += (
            f'<circle cx="{lx}" cy="{ly - 4}" r="5" fill="{colors[name]}"/>'
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
    user = gql(QUERY, {"login": USER})["user"]
    os.makedirs("assets", exist_ok=True)
    with open("assets/stats.svg", "w") as f:
        f.write(stats_card(user))
    with open("assets/langs.svg", "w") as f:
        f.write(langs_card(user))
    print("wrote assets/stats.svg and assets/langs.svg")


if __name__ == "__main__":
    main()
