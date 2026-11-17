"""Generate profile card SVGs (stats, languages, activity, highlights) into assets/.

Data source: GitHub GraphQL API.
Token: env GITHUB_TOKEN or GH_TOKEN; falls back to the authenticated gh CLI for local runs.
Usage: python .github/scripts/generate_cards.py
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = "Yumin-04"
ASSETS = Path(__file__).resolve().parents[2] / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    pullRequests { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

FONT = "'Segoe UI','Helvetica Neue',Arial,sans-serif"


def fetch() -> dict:
    """Use the Actions token when set; otherwise call the authenticated gh CLI (local run)."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-cards"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    else:
        try:
            out = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={QUERY}", "-F", f"login={LOGIN}"],
                capture_output=True, text=True, check=True, encoding="utf-8",
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            sys.exit(f"No GitHub token: set GITHUB_TOKEN or log in with gh. ({exc})")
        payload = json.loads(out.stdout)
    if "errors" in payload or not payload.get("data", {}).get("user"):
        sys.exit(f"GraphQL error: {payload.get('errors')}")
    return payload["data"]["user"]


def card(width: int, height: int, title: str, inner: str, gradient=("#1e1033", "#2f1450"), accent="#ff7ad9") -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{gradient[0]}"/>
      <stop offset="1" stop-color="{gradient[1]}"/>
    </linearGradient>
    <linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ff7ad9"/>
      <stop offset="1" stop-color="#9d6bff"/>
    </linearGradient>
  </defs>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="16" fill="url(#bg)" stroke="{accent}" stroke-opacity="0.45" stroke-width="2"/>
  <g font-family="{FONT}">
    <text x="28" y="44" font-size="20" font-weight="700" fill="{accent}">{escape(title)}</text>
{inner}
  </g>
</svg>
"""


def stats_card(user: dict) -> str:
    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    active = sum(1 for d in days if d["contributionCount"] > 0)
    rows = [
        ("Public Repositories", user["repositories"]["totalCount"]),
        ("Commits (last year)", cc["totalCommitContributions"]),
        ("Pull Requests", user["pullRequests"]["totalCount"]),
        ("Active Days (last year)", active),
        ("Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
    ]
    out = []
    for i, (label, value) in enumerate(rows):
        y = 84 + i * 30
        out.append(f'    <circle cx="34" cy="{y - 5}" r="4" fill="#ff7ad9"/>')
        out.append(f'    <text x="48" y="{y}" font-size="15" fill="#e9d5ff">{escape(label)}</text>')
        out.append(f'    <text x="448" y="{y}" font-size="16" font-weight="700" fill="#ffffff" text-anchor="end">{value:,}</text>')
    return card(480, 240, "Yumin's GitHub Stats", "\n".join(out))


def langs_card(user: dict) -> str:
    totals: dict[str, int] = {}
    colors: dict[str, str] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#999999"
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    out = []
    x = 28.0
    bar_w = 424.0
    out.append(f'    <clipPath id="barclip"><rect x="28" y="66" width="{bar_w}" height="20" rx="10"/></clipPath>')
    out.append('    <g clip-path="url(#barclip)">')
    for name, size in ranked:
        w = bar_w * size / grand
        out.append(f'      <rect x="{x:.1f}" y="66" width="{w:.1f}" height="20" fill="{colors[name]}"/>')
        x += w
    out.append("    </g>")
    for i, (name, size) in enumerate(ranked):
        col, row = i % 2, i // 2
        lx = 28 + col * 215
        ly = 126 + row * 32
        pct = 100 * size / grand
        out.append(f'    <circle cx="{lx + 6}" cy="{ly - 5}" r="6" fill="{colors[name]}"/>')
        out.append(f'    <text x="{lx + 20}" y="{ly}" font-size="14" fill="#e9d5ff">{escape(name)} {pct:.1f}%</text>')
    out.append('    <text x="28" y="214" font-size="11" fill="#c4b5fd">by code size, public repositories only</text>')
    return card(480, 240, "Most Used Languages", "\n".join(out))


def activity_card(user: dict) -> str:
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"][-26:]
    counts = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    peak = max(counts) or 1
    total = sum(counts)
    out = []
    base_y, max_h = 190, 100
    step = 424 / len(counts)
    for i, c in enumerate(counts):
        h = max(3.0, max_h * c / peak) if c else 3.0
        fill = 'url(#bar)' if c else '#ffffff'
        opacity = '1' if c else '0.12'
        out.append(
            f'    <rect x="{28 + i * step:.1f}" y="{base_y - h:.1f}" width="{step - 4:.1f}" height="{h:.1f}" rx="3" fill="{fill}" fill-opacity="{opacity}"/>'
        )
    out.append(f'    <text x="28" y="76" font-size="30" font-weight="800" fill="#ffffff">{total:,}</text>')
    out.append('    <text x="28" y="96" font-size="13" fill="#e9d5ff">contributions in the last 26 weeks</text>')
    out.append(f'    <text x="452" y="76" font-size="13" fill="#e9d5ff" text-anchor="end">busiest week: {peak:,}</text>')
    out.append(f'    <text x="28" y="214" font-size="11" fill="#c4b5fd">26 weeks ago</text>')
    out.append(f'    <text x="452" y="214" font-size="11" fill="#c4b5fd" text-anchor="end">updated {date.today().isoformat()}</text>')
    return card(480, 240, "Recent Activity", "\n".join(out))


def highlights_card() -> str:
    items = [
        ("SUMTECH 2026 Hackathon", "Top Excellence Award"),
        ("ESG Management Idea Contest", "Excellence Award (1st place)"),
        ("The KBO 9 Season 2025", "Excellence Award"),
        ("ADsP  |  SQLD", "Certified"),
    ]
    out = []
    for i, (name, detail) in enumerate(items):
        y = 84 + i * 40
        out.append(f'    <circle cx="36" cy="{y - 6}" r="5" fill="#fde047"/>')
        out.append(f'    <text x="52" y="{y}" font-size="15" font-weight="700" fill="#ffffff">{escape(name)}</text>')
        out.append(f'    <text x="52" y="{y + 18}" font-size="12.5" fill="#fff1f9">{escape(detail)}</text>')
    return card(480, 240, "Highlights", "\n".join(out), gradient=("#ff3fa4", "#ff9a3c"), accent="#fff1f9")


def main() -> None:
    user = fetch()
    ASSETS.mkdir(exist_ok=True)
    files = {
        "card-stats.svg": stats_card(user),
        "card-langs.svg": langs_card(user),
        "card-activity.svg": activity_card(user),
        "card-highlights.svg": highlights_card(),
    }
    for name, svg in files.items():
        (ASSETS / name).write_text(svg, encoding="utf-8", newline="\n")
        print("wrote", name)


if __name__ == "__main__":
    main()
