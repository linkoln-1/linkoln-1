#!/usr/bin/env python3
"""Generate profile stat cards (assets/*.svg) from GitHub data.

Aggregates PUBLIC + PRIVATE repos via `gh api graphql` (token stays in gh).
Only aggregate numbers are published — no private repo names or details.

Usage: python3 scripts/update_stats.py
"""
import json
import subprocess

BG = "#0d1117"
FG = "#c9d1d9"
ACCENT = "#61DAFB"
MUTED = "#8b949e"
FONT = "'Segoe UI', Ubuntu, Sans-Serif"
CARD_W = 420
CARD_H = 195
TOP_LANGS = 8


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


def main() -> None:
    stats = fetch_stats()
    with open("assets/stats-card.svg", "w") as f:
        f.write(render_stats_card(stats))
    with open("assets/langs-card.svg", "w") as f:
        f.write(render_langs_card(stats["langs"]))
    print(f"commits={stats['commits']} repos={stats['repos']} (private={stats['private_repos']})")
    top = sorted(stats["langs"].items(), key=lambda kv: kv[1]["size"], reverse=True)[:TOP_LANGS]
    total = sum(v["size"] for v in stats["langs"].values()) or 1
    print(", ".join(f"{n} {100 * i['size'] / total:.1f}%" for n, i in top))


if __name__ == "__main__":
    main()
