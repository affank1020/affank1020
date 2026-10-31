#!/usr/bin/env python3
"""Small, dependency-free GitHub profile card generator.

Activity is GitHub's trailing-year eligible contribution count.
Language shares are calculated from all public repositories, each weighted equally.
"""

import json
import os
import re
from collections import defaultdict
from html import escape
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen

USER = "affank1020"
LANGS = ("TypeScript", "Python", "Kotlin", "Rust", "JavaScript", "C#", "Swift")
COLORS = {
    "TypeScript": "#6f8ea3",
    "Python": "#6f9f95",
    "Kotlin": "#a67fa8",
    "Rust": "#a68167",
    "JavaScript": "#b09b63",
    "C#": "#8d79b3",
    "Swift": "#c27c6d",
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


def public_repositories():
    """Discover all currently public, user-owned repositories (including new ones)."""
    repos = []
    page = 1
    while True:
        page_data = api(
            f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}"
        )
        if not isinstance(page_data, list):
            raise RuntimeError("Unexpected response when listing public repositories")
        for item in page_data:
            if item.get("owner", {}).get("login") == USER and item.get("private") is False:
                repos.append(item["name"])
        if len(page_data) < 100:
            break
        page += 1
    if not repos:
        raise RuntimeError("No public repositories found")
    return sorted(set(repos), key=str.casefold)


def languages():
    """Use all public repositories; weight each source-bearing repository equally."""
    repos = public_repositories()
    totals = defaultdict(float)
    counted = 0
    without_source = []
    for repo in repos:
        langs = api(
            f"https://api.github.com/repos/{USER}/{quote(repo, safe='')}/languages"
        )
        if not isinstance(langs, dict):
            raise RuntimeError(f"Unexpected languages response for {repo}")
        source = {lang: int(langs[lang]) for lang in LANGS
                  if lang in langs and int(langs[lang]) > 0}
        size = sum(source.values())
        # Empty repos, binaries, assets and documentation contribute no code share.
        if not size:
            without_source.append(repo)
            continue
        counted += 1
        for lang, amount in source.items():
            totals[lang] += amount / size
    if counted == 0:
        raise RuntimeError("No public repositories contain tracked source languages")
    shares = {lang: 100 * weight / counted for lang, weight in totals.items()}
    return dict(sorted(shares.items(), key=lambda item: -item[1])), repos, without_source


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
            f'rx="4" fill="{color}" fill-opacity="0.42" '
            f'stroke="{color}" stroke-opacity="0.65"/>')
    if inner_width >= 105 and inner_height >= 48:
        body += text(inner_x + 13, inner_y + 26, name, 14, FG, 600)
        body += text(inner_x + 13, inner_y + 45, f"{percent:.1f}%", 12, MUTED)
    elif inner_width >= 68 and inner_height >= 26:
        body += text(inner_x + 9, inner_y + 19, name, 12, FG, 500)
    return body


def language_card(shares):
    """Weighted treemap on the left, legible ranked legend on the right."""
    body = text(28, 35, "Languages", 19, FG, 600)
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
    shares, repos, skipped = languages()
    out = Path("assets/profile")
    out.mkdir(parents=True, exist_ok=True)
    # Unique image URLs avoid stale GitHub proxy/browser caches on the profile.
    readme_path = Path("README.md")
    readme = readme_path.read_text(encoding="utf-8")
    cards = {
        "activity": activity_card(metrics),
        "languages": language_card(shares),
    }
    for name, content in cards.items():
        digest = sha256(content.encode("utf-8")).hexdigest()[:12]
        filename = f"{name}-{digest}.svg"
        for old_file in out.glob(f"{name}*.svg"):
            if old_file.name != filename:
                old_file.unlink()
        (out / filename).write_text(content, encoding="utf-8")
        pattern = rf"\./assets/profile/{name}(?:-[a-f0-9]{{12}})?\.svg"
        readme, replaced = re.subn(pattern, f"./assets/profile/{filename}", readme)
        if replaced != 1:
            raise RuntimeError(f"Expected exactly one {name} card reference in README")
    readme_path.write_text(readme, encoding="utf-8")
    print("Activity:", metrics)
    print("Languages:", {k: round(v, 1) for k, v in shares.items()})
    print("Public repositories:", len(repos), repos, "without tracked source:", skipped)


if __name__ == "__main__":
    main()
