#!/usr/bin/env python3
"""Generate profile stat cards (assets/*.svg) from GitHub data.

Aggregates PUBLIC + PRIVATE repos via `gh api graphql` (token stays in gh).
Only aggregate numbers are published — no private repo names or details.

Usage: python3 scripts/update_stats.py
"""
import json
import subprocess
from datetime import datetime, timedelta, timezone

BG = "#0d1117"
FG = "#c9d1d9"
ACCENT = "#61DAFB"
MUTED = "#8b949e"
FONT = "'Segoe UI', Ubuntu, Sans-Serif"
CARD_W = 420
CARD_H = 195
TOP_LANGS = 8
ACTIVITY_DAYS = 182
ACT_W = 880
ACT_H = 210


def gql(query: str, **variables) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        cmd += ["-f", f"{key}={value}"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["data"]


def fetch_stats() -> dict:
    viewer = gql("query { viewer { id login } }")["viewer"]

    repos = []
    cursor = "null"
    while True:
        data = gql(
            """
            query($id: ID) {
              viewer {
                repositories(first: 50, after: %s, ownerAffiliations: OWNER, isFork: false) {
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    isPrivate
                    stargazerCount
                    languages(first: 10) { edges { size node { name color } } }
                    defaultBranchRef {
                      target { ... on Commit { history(author: {id: $id}) { totalCount } } }
                    }
                  }
                }
              }
            }
            """
            % cursor,
            id=viewer["id"],
        )["viewer"]["repositories"]
        repos += data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = f'"{data["pageInfo"]["endCursor"]}"'

    totals = gql(
        """
        query {
          viewer {
            pullRequests { totalCount }
            issues { totalCount }
            repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST]) { totalCount }
          }
        }
        """
    )["viewer"]

    commits = 0
    stars = 0
    langs: dict[str, dict] = {}
    for repo in repos:
        stars += repo["stargazerCount"]
        branch = repo.get("defaultBranchRef")
        if branch and branch.get("target"):
            commits += branch["target"]["history"]["totalCount"]
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            entry = langs.setdefault(name, {"size": 0, "color": edge["node"]["color"] or MUTED})
            entry["size"] += edge["size"]

    return {
        "commits": commits,
        "stars": stars,
        "repos": len(repos),
        "private_repos": sum(1 for r in repos if r["isPrivate"]),
        "prs": totals["pullRequests"]["totalCount"],
        "issues": totals["issues"]["totalCount"],
        "contributed": totals["repositoriesContributedTo"]["totalCount"],
        "langs": langs,
    }


def render_stats_card(stats: dict) -> str:
    rows = [
        ("Total Commits (incl. private)", stats["commits"]),
        ("Repositories (incl. private)", stats["repos"]),
        ("Total Stars", stats["stars"]),
        ("Pull Requests", stats["prs"]),
        ("Contributed To", stats["contributed"]),
    ]
    row_svg = ""
    for i, (label, value) in enumerate(rows):
        y = 70 + i * 25
        row_svg += (
            f'<circle cx="32" cy="{y - 4}" r="3" fill="{ACCENT}"/>'
            f'<text x="45" y="{y}" fill="{FG}" font-size="14">{label}</text>'
            f'<text x="{CARD_W - 30}" y="{y}" fill="{ACCENT}" font-size="14" '
            f'font-weight="600" text-anchor="end">{value}</text>'
        )
    return f"""<svg width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">
  <rect width="{CARD_W}" height="{CARD_H}" rx="10" fill="{BG}"/>
  <text x="25" y="35" fill="{ACCENT}" font-size="18" font-weight="600">GitHub Stats — all repos</text>
  {row_svg}
</svg>
"""


def render_langs_card(langs: dict) -> str:
    total = sum(v["size"] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:TOP_LANGS]

    bar_x, bar_w, bar_y = 25, CARD_W - 50, 55
    x = float(bar_x)
    bar_svg = f'<mask id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5" fill="white"/></mask><g mask="url(#bar)">'
    for name, info in top:
        width = bar_w * info["size"] / total
        bar_svg += f'<rect x="{x:.1f}" y="{bar_y}" width="{width + 1:.1f}" height="10" fill="{info["color"]}"/>'
        x += width
    bar_svg += "</g>"

    legend_svg = ""
    col_w = (CARD_W - 50) / 2
    for i, (name, info) in enumerate(top):
        pct = 100 * info["size"] / total
        lx = 25 + (i % 2) * col_w
        ly = 95 + (i // 2) * 24
        legend_svg += (
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{info["color"]}"/>'
            f'<text x="{lx + 18}" y="{ly}" fill="{FG}" font-size="13">{name}</text>'
            f'<text x="{lx + col_w - 20}" y="{ly}" fill="{MUTED}" font-size="13" text-anchor="end">{pct:.1f}%</text>'
        )
    return f"""<svg width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">
  <rect width="{CARD_W}" height="{CARD_H}" rx="10" fill="{BG}"/>
  <text x="25" y="35" fill="{ACCENT}" font-size="18" font-weight="600">Languages — all repos</text>
  {bar_svg}
  {legend_svg}
</svg>
"""


def fetch_activity() -> list[dict]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=ACTIVITY_DAYS)
    data = gql(
        """
        query($from: DateTime!, $to: DateTime!) {
          viewer {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar {
                weeks { contributionDays { date contributionCount } }
              }
            }
          }
        }
        """,
        **{"from": start.isoformat(), "to": now.isoformat()},
    )
    weeks = data["viewer"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [day for week in weeks for day in week["contributionDays"]]


def render_activity_card(days: list[dict]) -> str:
    pad_left, pad_right, pad_top, pad_bottom = 45, 20, 55, 30
    plot_w = ACT_W - pad_left - pad_right
    plot_h = ACT_H - pad_top - pad_bottom
    counts = [d["contributionCount"] for d in days]
    peak = max(counts) or 1
    step = plot_w / max(len(days) - 1, 1)

    def point(i: int, count: int) -> tuple[float, float]:
        return pad_left + i * step, pad_top + plot_h * (1 - count / peak)

    coords = [point(i, c) for i, c in enumerate(counts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    baseline = pad_top + plot_h
    area = f"{pad_left},{baseline} {line} {coords[-1][0]:.1f},{baseline}"

    months_svg = ""
    for i, day in enumerate(days):
        if day["date"][8:10] == "01":
            label = datetime.fromisoformat(day["date"]).strftime("%b")
            months_svg += (
                f'<text x="{coords[i][0]:.1f}" y="{ACT_H - 10}" fill="{MUTED}" '
                f'font-size="12" text-anchor="middle">{label}</text>'
            )

    grid_svg = ""
    for value in (0, peak):
        y = pad_top + plot_h * (1 - value / peak)
        grid_svg += (
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{ACT_W - pad_right}" y2="{y:.1f}" '
            f'stroke="{MUTED}" stroke-opacity="0.2" stroke-dasharray="3,3"/>'
            f'<text x="{pad_left - 8}" y="{y + 4:.1f}" fill="{MUTED}" font-size="11" '
            f'text-anchor="end">{value}</text>'
        )

    last_x, last_y = coords[-1]
    return f"""<svg width="{ACT_W}" height="{ACT_H}" viewBox="0 0 {ACT_W} {ACT_H}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">
  <rect width="{ACT_W}" height="{ACT_H}" rx="10" fill="{BG}"/>
  <text x="25" y="35" fill="{ACCENT}" font-size="18" font-weight="600">Contribution Activity — last 6 months</text>
  {grid_svg}
  <polygon points="{area}" fill="{ACCENT}" fill-opacity="0.12"/>
  <polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="1.5" stroke-linejoin="round"/>
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="#ffffff"/>
  {months_svg}
</svg>
"""


def main() -> None:
    stats = fetch_stats()
    with open("assets/stats-card.svg", "w") as f:
        f.write(render_stats_card(stats))
    with open("assets/langs-card.svg", "w") as f:
        f.write(render_langs_card(stats["langs"]))
    days = fetch_activity()
    with open("assets/activity-card.svg", "w") as f:
        f.write(render_activity_card(days))
    print(f"commits={stats['commits']} repos={stats['repos']} (private={stats['private_repos']})")
    top = sorted(stats["langs"].items(), key=lambda kv: kv[1]["size"], reverse=True)[:TOP_LANGS]
    total = sum(v["size"] for v in stats["langs"].values()) or 1
    print(", ".join(f"{n} {100 * i['size'] / total:.1f}%" for n, i in top))


if __name__ == "__main__":
    main()
