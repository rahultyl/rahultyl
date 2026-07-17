#!/usr/bin/env python3
"""Generate the self-hosted GitHub overview card as SVGs (light + dark).

Uses only the REST API and the public contributions page (the Actions
GITHUB_TOKEN erratically rejects GraphQL and returns empty search results;
last-known-good search numbers are cached in assets/stats.json so a
degraded run can refresh the calendar without writing zeros).
Writes assets/overview-light.svg and assets/overview-dark.svg.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "")
USER = os.environ.get("USERNAME", "rahultyl")
CACHE = "assets/stats.json"
FONT = "'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"

# Theme-adaptive palettes; single gradient accent, neutral inks.
DARK = {
    "surface": "#16161e", "border": "#262939",
    "ink": "#e6e9f5", "ink2": "#9aa1c0", "muted": "#626880",
    "grad_a": "#7aa2f7", "grad_b": "#bb9af7",
}
LIGHT = {
    "surface": "#ffffff", "border": "#e2e6f0",
    "ink": "#1a1f36", "ink2": "#5b6178", "muted": "#8a91ab",
    "grad_a": "#2563eb", "grad_b": "#7c3aed",
}

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


def weekly_calendar(page):
    """Parse the contribution calendar into weekly totals (oldest→newest)."""
    days = {}
    for m in re.finditer(r'<td[^>]*class="ContributionCalendar-day"[^>]*>', page):
        tag = m.group(0)
        i = re.search(r'id="([^"]+)"', tag)
        d = re.search(r'data-date="([\d-]+)"', tag)
        lv = re.search(r'data-level="(\d)"', tag)
        if i and d:
            days[i.group(1)] = [d.group(1), int(lv.group(1)) if lv else 0]
    counts = {}
    for m in re.finditer(r"<tool-tip[^>]*for=\"([^\"]+)\"[^>]*>([^<]*)</tool-tip>", page):
        tid, text = m.groups()
        c = re.match(r"\s*([\d,]+|No)\s+contribution", text)
        if tid in days and c:
            counts[tid] = 0 if c.group(1) == "No" else int(c.group(1).replace(",", ""))
    seq = sorted((date, counts.get(tid, level)) for tid, (date, level) in days.items())
    daily = [n for _, n in seq]
    return [sum(daily[i:i + 7]) for i in range(0, len(daily), 7)] or [0]


def collect():
    profile = get(f"https://api.github.com/users/{USER}")
    repos = get(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")

    # Public contributions page — also reflects the "include private
    # contributions" profile setting, and works with no token at all.
    page = get(f"https://github.com/users/{USER}/contributions")
    m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", page)
    total = int(m.group(1).replace(",", "")) if m else 0
    weeks = weekly_calendar(page)

    since = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    commit_search = search(
        f"https://api.github.com/search/commits?q=author:{USER}+author-date:%3E{since}&per_page=100"
    )
    commits = commit_search.get("total_count", 0)
    contributed = len({item["repository"]["full_name"] for item in commit_search.get("items", [])})
    prs = search(f"https://api.github.com/search/issues?q=author:{USER}+type:pr").get("total_count", 0)
    issues = search(f"https://api.github.com/search/issues?q=author:{USER}+type:issue").get("total_count", 0)

    if total and not (commits or prs):
        # Degraded search (Actions app token): fall back to cached numbers
        # rather than rendering zeros; hard-fail with no cache to fall on.
        try:
            with open(CACHE) as f:
                cached = json.load(f)
            commits, prs = cached["commits"], cached["prs"]
            issues, contributed = cached["issues"], cached["contributed"]
        except (OSError, KeyError, ValueError):
            raise SystemExit("search degraded and no cache; refusing to write zeros")

    sizes = {}
    lang_repos = [r for r in repos if not r["fork"]] or repos
    for repo in lang_repos:
        for lang, size in get(f"https://api.github.com/repos/{repo['full_name']}/languages").items():
            sizes[lang] = sizes.get(lang, 0) + size
    langs = sorted(sizes.items(), key=lambda kv: -kv[1])[:5]

    return {
        "name": profile.get("name") or USER,
        "total": total,
        "weeks": weeks,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "contributed": max(contributed, 1),
        "langs": langs,
    }


def fmt(n):
    return f"{n:,}"


def sparkline(weeks, p, x, y, w, h):
    """Animated area sparkline: the line draws itself in, the area fades
    up behind it, and the endpoint dot pulses like a live indicator."""
    peak = max(weeks) or 1
    n = len(weeks)
    pts = []
    for i, v in enumerate(weeks):
        px = x + w * i / max(n - 1, 1)
        py = y + h - (h - 2) * v / peak
        pts.append((px, py))
    length = sum(
        ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        for (x1, y1), (x2, y2) in zip(pts, pts[1:])
    )
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{x},{y + h} {line} {x + w},{y + h}"
    ex, ey = pts[-1]
    return f"""
    <style>
      .line {{ stroke-dasharray: {length:.0f}; stroke-dashoffset: {length:.0f};
        animation: draw 2.4s ease-out forwards; }}
      .area {{ opacity: 0; animation: rise 1s ease-out 1.5s forwards; }}
      .dot {{ opacity: 0; animation: pop 0.4s ease-out 2.3s forwards; }}
      .ping {{ transform-origin: {ex:.1f}px {ey:.1f}px;
        animation: ping 2s ease-out 2.8s infinite; opacity: 0; }}
      @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
      @keyframes rise {{ to {{ opacity: 1; }} }}
      @keyframes pop {{ to {{ opacity: 1; }} }}
      @keyframes ping {{
        0% {{ opacity: 0.7; transform: scale(0.4); }}
        70% {{ opacity: 0; transform: scale(2.4); }}
        100% {{ opacity: 0; transform: scale(2.4); }}
      }}
      @media (prefers-reduced-motion: reduce) {{
        .line {{ stroke-dasharray: none; stroke-dashoffset: 0; animation: none; }}
        .area, .dot {{ opacity: 1; animation: none; }}
        .ping {{ animation: none; opacity: 0; }}
      }}
    </style>
    <polygon class="area" points="{area}" fill="url(#fade)"/>
    <polyline class="line" points="{line}" fill="none" stroke="url(#accent)" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle class="ping" cx="{ex:.1f}" cy="{ey:.1f}" r="6" fill="none" stroke="{p["grad_b"]}" stroke-width="1.5"/>
    <circle class="dot" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{p["grad_b"]}" stroke="{p["surface"]}" stroke-width="2"/>"""


def overview_card(d, p):
    W, H = 846, 232
    rows = [
        ("PULL REQUESTS", d["prs"]),
        ("ISSUES", d["issues"]),
        ("REPOS", d["contributed"]),
    ]
    row_svg = ""
    for i, (label, val) in enumerate(rows):
        ry = 96 + i * 40
        row_svg += (
            f'<text x="560" y="{ry}" fill="{p["muted"]}" font-size="10" font-weight="600" letter-spacing="1">{label}</text>'
            f'<text x="814" y="{ry}" fill="{p["ink"]}" font-size="20" font-weight="600" text-anchor="end" '
            f'style="font-variant-numeric: tabular-nums">{fmt(val)}</text>'
        )

    # language strip: 2px gaps, GitHub language colors, labels in ink
    strip_y, strip_x, strip_w = 196, 32, 300
    total_size = sum(s for _, s in d["langs"]) or 1
    x = strip_x
    strip = f'<clipPath id="strip"><rect x="{strip_x}" y="{strip_y}" width="{strip_w}" height="6" rx="3"/></clipPath><g clip-path="url(#strip)">'
    for name, size in d["langs"]:
        w = (strip_w - 2 * (len(d["langs"]) - 1)) * size / total_size
        strip += f'<rect x="{x:.1f}" y="{strip_y}" width="{w:.1f}" height="6" fill="{LANG_COLORS.get(name, "#8b949e")}"/>'
        x += w + 2
    strip += "</g>"
    lx = strip_x + strip_w + 16
    for name, size in d["langs"][:3]:
        pct = 100 * size / total_size
        strip += (
            f'<circle cx="{lx}" cy="{strip_y + 3}" r="4" fill="{LANG_COLORS.get(name, "#8b949e")}"/>'
            f'<text x="{lx + 10}" y="{strip_y + 7}" fill="{p["ink2"]}" font-size="11">{name} {pct:.0f}%</text>'
        )
        lx += 10 + 7 * len(f"{name} {pct:.0f}%") + 18

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{d["name"]}: {fmt(d["total"])} contributions in the last year">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{p["grad_a"]}"/>
      <stop offset="100%" stop-color="{p["grad_b"]}"/>
    </linearGradient>
    <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{p["grad_a"]}" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="{p["grad_b"]}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="hero" x1="32" y1="0" x2="300" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="{p["grad_a"]}"/>
      <stop offset="100%" stop-color="{p["grad_b"]}"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{p["surface"]}" stroke="{p["border"]}"/>
  <g font-family="{FONT}">
    <text x="32" y="44" fill="{p["muted"]}" font-size="10" font-weight="600" letter-spacing="1.5">CONTRIBUTIONS · LAST 12 MONTHS</text>
    <text x="32" y="92" fill="url(#hero)" font-size="42" font-weight="700" style="font-variant-numeric: tabular-nums">{fmt(d["total"])}</text>
    {sparkline(d["weeks"], p, 32, 108, 448, 60)}
    <line x1="524" y1="36" x2="524" y2="196" stroke="{p["border"]}"/>
    <text x="560" y="44" fill="{p["muted"]}" font-size="10" font-weight="600" letter-spacing="1.5">LAST YEAR · PUBLIC</text>
    {row_svg}
    {strip}
  </g>
</svg>
"""


def main():
    d = collect()
    os.makedirs("assets", exist_ok=True)
    with open("assets/overview-light.svg", "w") as f:
        f.write(overview_card(d, LIGHT))
    with open("assets/overview-dark.svg", "w") as f:
        f.write(overview_card(d, DARK))
    with open(CACHE, "w") as f:
        json.dump({k: d[k] for k in ("commits", "prs", "issues", "contributed")}, f)
    print(f"wrote overview cards: {json.dumps({k: v for k, v in d.items() if k not in ('langs', 'weeks')})}")


if __name__ == "__main__":
    main()
