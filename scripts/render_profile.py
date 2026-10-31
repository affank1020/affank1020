#!/usr/bin/env python3
"""Small, dependency-free GitHub profile card generator.

Activity is GitHub's trailing-year eligible contribution count.
Language shares are calculated from selected repos, each weighted equally.
"""

import json
import os
from collections import defaultdict
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

USER = "affank1020"
REPOS = ("atlas", "relay", "EcoPrompt", "ascii-donut", "chatflow", "benchmark", "agent-workflows", "Football-Match-Simulation")
LANGS = ("TypeScript", "Python", "Kotlin", "Rust", "JavaScript", "C#", "Swift")
COLORS = {
    "TypeScript": "#9bb3c9",
    "Python": "#b8c4aa",
    "Kotlin": "#b8a8cc",
    "Rust": "#c6b09d",
    "JavaScript": "#c8c0a4",
    "C#": "#b7a9bb",
    "Swift": "#b4a6a1",
}
BG, BORDER, FG, MUTED = "#0d1117", "#30363d", "#e6edf3", "#8b949e"


def api(url, payload=None):
    token = os.environ["GITHUB_TOKEN"]
    req = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "affank1020-profile",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API returned {exc.code} for {url}") from exc


def activity():
    query = """query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
        }
      }
    }"""
    result = api("https://api.github.com/graphql",
                 {"query": query, "variables": {"login": USER}})
    if result.get("errors"):
        raise RuntimeError(str(result["errors"]))
    data = result.get("data", {}).get("user")
    if not data:
        raise RuntimeError("GitHub contribution data unavailable")
    collection = data["contributionsCollection"]
    return {
        "Commits": collection["totalCommitContributions"],
        "Pull requests": collection["totalPullRequestContributions"],
        "Reviews": collection["totalPullRequestReviewContributions"],
    }


def languages():
    """Each repository gets equal weight; source bytes determine its internal mix."""
    result = defaultdict(float)
    for repo in REPOS:
        langs = api(f"https://api.github.com/repos/{USER}/{repo}/languages")
        selected = {k: int(langs[k]) for k in LANGS if k in langs and int(langs[k]) > 0}
        total = sum(selected.values())
        if not total:
            raise RuntimeError(f"No tracked source language in {repo}")
        for lang, amount in selected.items():
            result[lang] += 100 * amount / total / len(REPOS)
    return dict(sorted(result.items(), key=lambda item: -item[1]))


def text(x, y, value, size=13, color=MUTED, weight=400, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>')


def frame(height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="820" height="{height}" '
            f'viewBox="0 0 820 {height}" role="img">'
            f'<rect x="0.5" y="0.5" width="819" height="{height - 1}" '
            f'rx="9" fill="{BG}" stroke="{BORDER}"/>'
            '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">'
            f'{body}</g></svg>\n')


def activity_card(metrics):
    body = text(28, 35, "Activity", 19, FG, 600)
    body += text(792, 34, "Last 12 months", 12, anchor="end")
    for i, (name, value) in enumerate(metrics.items()):
        x = 28 + i * 265
        if i:
            body += f'<path d="M{x - 19} 60v76" stroke="{BORDER}"/>'
        body += text(x, 109, f"{value:,}", 35, FG, 600)
        body += text(x, 132, name)
    return frame(156, body)


def treemap(items, x, y, width, height):
    """Partition the rectangle proportionally, splitting along the longer side."""
    if not items:
        return ""
    if len(items) > 1:
        total = sum(amount for _, amount in items)
        running = 0.0
        best_index, best_delta = 1, float("inf")
        for index in range(1, len(items)):
            running += items[index - 1][1]
            delta = abs(running / total - 0.5)
            if delta < best_delta:
                best_index, best_delta = index, delta
        left, right = items[:best_index], items[best_index:]
        fraction = sum(amount for _, amount in left) / total
        if width >= height:
            split = width * fraction
            return (treemap(left, x, y, split, height)
                    + treemap(right, x + split, y, width - split, height))
        split = height * fraction
        return (treemap(left, x, y, width, split)
                + treemap(right, x, y + split, width, height - split))

    name, percent = items[0]
    # Leave a narrow gutter between adjacent tiles.
    inner_x, inner_y = x + 1.5, y + 1.5
    inner_width, inner_height = width - 3, height - 3
    if inner_width <= 0 or inner_height <= 0:
        return ""
    color = COLORS[name]
    body = (f'<rect x="{inner_x:.2f}" y="{inner_y:.2f}" '
            f'width="{inner_width:.2f}" height="{inner_height:.2f}" '
            f'rx="4" fill="{color}" fill-opacity="0.27" '
            f'stroke="{color}" stroke-opacity="0.55"/>')
    if inner_width >= 105 and inner_height >= 48:
        body += text(inner_x + 13, inner_y + 26, name, 14, FG, 600)
        body += text(inner_x + 13, inner_y + 45, f"{percent:.1f}%", 12, MUTED)
    elif inner_width >= 68 and inner_height >= 26:
        body += text(inner_x + 9, inner_y + 19, name, 12, FG, 500)
    return body


def language_card(shares):
    """Weighted treemap on the left, legible ranked legend on the right."""
    body = text(28, 35, "Languages", 19, FG, 600)
    body += text(792, 34, f"{len(REPOS)} selected repositories", 12, anchor="end")
    ordered = list(shares.items())
    body += treemap(ordered, 28, 58, 464, 235)
    for index, (lang, percent) in enumerate(ordered):
        x, y = 530, 78 + index * 33
        body += f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{COLORS[lang]}"/>'
        body += text(x + 20, y, lang, 13, FG)
        value = "<0.1%" if 0 < percent < 0.05 else f"{percent:.1f}%"
        body += text(792, y, value, 13, MUTED, anchor="end")
    return frame(314, body)

def main():
    metrics = activity()
    shares = languages()
    out = Path("assets/profile")
    out.mkdir(parents=True, exist_ok=True)
    (out / "activity.svg").write_text(activity_card(metrics), encoding="utf-8")
    (out / "languages.svg").write_text(language_card(shares), encoding="utf-8")
    print("Activity:", metrics)
    print("Languages:", {k: round(v, 1) for k, v in shares.items()})


if __name__ == "__main__":
    main()
