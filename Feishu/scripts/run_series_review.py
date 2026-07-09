#!/usr/bin/env python3
"""Static review gate for Writer series notes.

This intentionally stays local: it reads the topic manifest and article files,
then writes a daily review report under the topic's openclaw/reviews directory.
Manual spot-check sections appended by agents are preserved across re-runs.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


TOPIC_MANIFESTS = {
    "android-memory": Path(
        "/Users/gracker/Library/Mobile Documents/iCloud~md~obsidian/Documents/Writer/"
        "android-memory/openclaw/topic-manifest.json"
    ),
    "rendering-pipelines": Path(
        "/Users/gracker/Library/Mobile Documents/iCloud~md~obsidian/Documents/Writer/"
        "rendering_pipelines/openclaw/topic-manifest.json"
    ),
}


LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FIRST_PARTY_RE = re.compile(
    r"https?://(?:android\.googlesource\.com|source\.android\.com|developer\.android\.com)[^) >]+"
)
TODO_RE = re.compile(r"TODO|FIXME|待补")
MANUAL_RE = re.compile(r"(?m)^## Manual Spot Check\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, choices=sorted(TOPIC_MANIFESTS))
    parser.add_argument("--date", required=True)
    return parser.parse_args()


def load_manifest(topic: str) -> dict:
    manifest_path = TOPIC_MANIFESTS[topic]
    with manifest_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def local_links(markdown: str) -> list[str]:
    links: list[str] = []
    for raw in LINK_RE.findall(markdown):
        if re.match(r"^[a-z]+://", raw) or raw.startswith("<http") or raw.startswith("#"):
            continue
        links.append(raw.split("#", 1)[0])
    return links


def article_order(path: Path, prefix: str) -> int:
    match = re.match(rf"{re.escape(prefix)}(\d+)[_-]?", path.name)
    if not match:
        raise ValueError(f"article filename does not match prefix {prefix}: {path.name}")
    return int(match.group(1))


def has_reading_nav(text: str) -> bool:
    if "## 阅读导航" not in text:
        return False
    nav_start = text.find("## 阅读导航")
    next_h2 = text.find("\n## ", nav_start + 1)
    nav_text = text[nav_start : next_h2 if next_h2 != -1 else len(text)]
    return bool(local_links(nav_text))


def article_snapshot(path: Path, root: Path, prefix: str) -> dict:
    text = path.read_text(encoding="utf-8")
    links = local_links(text)
    broken = []
    for link in links:
        if not link:
            continue
        target = (path.parent / link).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            broken.append(link)
            continue
        if not target.exists():
            broken.append(link)
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.name)
    return {
        "source_item_id": path.name,
        "title": title,
        "order": article_order(path, prefix),
        "word_count": len(text),
        "heading_count": len(re.findall(r"^#{2,6}\s+", text, flags=re.M)),
        "source_evidence_count": len(FIRST_PARTY_RE.findall(text)),
        "external_link_count": sum(
            1 for raw in LINK_RE.findall(text) if re.match(r"^[a-z]+://", raw)
        ),
        "local_link_count": len(links),
        "broken_local_links": broken,
        "todo_count": len(TODO_RE.findall(text)),
        "has_series_nav": has_reading_nav(text),
        "path": str(path),
    }


def find_articles(topic: dict) -> list[Path]:
    root = Path(topic["path"])
    prefix = topic.get("order_prefix", "S")
    articles = []
    for pattern in topic.get("include", [f"{prefix}*.md"]):
        for path in root.glob(pattern):
            if path.is_file() and re.match(rf"{re.escape(prefix)}\d+", path.name):
                articles.append(path)
    return sorted(set(articles), key=lambda p: article_order(p, prefix))


def expected_orders(orders: list[int]) -> list[int]:
    if not orders:
        return []
    return list(range(min(orders), max(orders) + 1))


def topic_article_title(topic: dict) -> str:
    return topic.get("title") or topic.get("feishu_root") or topic.get("id", "Writer Series")


def preserve_manual_sections(report_path: Path) -> str:
    if not report_path.exists():
        return ""
    text = report_path.read_text(encoding="utf-8")
    match = MANUAL_RE.search(text)
    if not match:
        return ""
    return "\n\n" + text[match.start() :].strip() + "\n"


def build_report(manifest: dict, snapshots: list[dict], date: str, manual_sections: str) -> str:
    topic = manifest["topic"]
    source_issues = []
    architecture_issues = []
    editorial_issues = []

    orders = [item["order"] for item in snapshots]
    expected = expected_orders(orders)
    if orders != expected:
        architecture_issues.append(
            f"Series order is not contiguous: observed={orders}, expected={expected}"
        )
    for item in snapshots:
        if item["source_evidence_count"] < 3:
            source_issues.append(
                f"{item['source_item_id']}: source anchors below floor "
                f"({item['source_evidence_count']} < 3)"
            )
        if item["broken_local_links"]:
            architecture_issues.append(
                f"{item['source_item_id']}: broken local links={item['broken_local_links']}"
            )
        if not item["has_series_nav"]:
            architecture_issues.append(f"{item['source_item_id']}: missing reading navigation")
        if item["todo_count"]:
            editorial_issues.append(
                f"{item['source_item_id']}: TODO/FIXME/待补 markers={item['todo_count']}"
            )

    issues = source_issues + architecture_issues + editorial_issues
    verdict = "pass" if not issues else "fail"
    blocking = len(issues)
    total_sources = sum(item["source_evidence_count"] for item in snapshots)
    min_sources = min(item["source_evidence_count"] for item in snapshots)
    max_sources = max(item["source_evidence_count"] for item in snapshots)
    local_total = sum(item["local_link_count"] for item in snapshots)
    broken_total = sum(len(item["broken_local_links"]) for item in snapshots)
    nav_count = sum(1 for item in snapshots if item["has_series_nav"])
    todos = sum(item["todo_count"] for item in snapshots)
    shortest = min(snapshots, key=lambda item: item["word_count"])
    suggested = sorted(
        snapshots,
        key=lambda item: (item["source_evidence_count"], item["local_link_count"], item["word_count"]),
    )[:3]

    lines = [
        f"# {topic_article_title(topic)} Daily Review - {date}",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- article_count: {len(snapshots)}",
        f"- repo: `{topic['repo']}`",
        f"- feishu_root: `{topic['feishu_root']}`",
        "",
        "## Review Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- blocking_issues: {blocking}",
        f"- total_issues: {len(issues)}",
        f"- source_issues: {len(source_issues)}",
        f"- architecture_issues: {len(architecture_issues)}",
        f"- editorial_issues: {len(editorial_issues)}",
        "",
        "## Review Evidence",
        "",
        "- Source floor: "
        f"{sum(1 for item in snapshots if item['source_evidence_count'] >= 3)}/{len(snapshots)} "
        f"articles have at least 3 first-party source anchors; min={min_sources}, "
        f"max={max_sources}, total={total_sources}.",
        f"- Local links: checked {local_total} markdown links; broken={broken_total}.",
        f"- Structure: series navigation present in {nav_count}/{len(snapshots)} articles; "
        f"order={expected[0] if expected else 0}-{expected[-1] if expected else 0}; "
        f"contiguous={'yes' if orders == expected else 'no'}.",
        f"- Editorial sweep: TODO/FIXME/待补 markers={todos}; "
        f"shortest={shortest['source_item_id']} ({shortest['word_count']} chars/words).",
        "- Scope limit: static review checks coverage and hygiene; claim-level correctness still "
        "requires manual source reading.",
        "",
        "## Suggested Spot Checks",
        "",
    ]
    for item in suggested:
        lines.append(
            f"- {item['source_item_id']}: source={item['source_evidence_count']}, "
            f"local_links={item['local_link_count']}, chars/words={item['word_count']}."
        )
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            "- No static-failure follow-up actions. Use the suggested spot checks above for "
            "manual source-reading rotation."
            if not issues
            else "- Fix blocking static issues before publishing.",
            "",
            f"## Source Review ({len(source_issues)} issues)",
            "",
        ]
    )
    lines.extend([f"- {issue}" for issue in source_issues] or ["- PASS: source evidence checks passed."])
    lines.extend(["", "## Architecture Review", ""])
    lines.extend([f"- {issue}" for issue in architecture_issues] or ["- PASS: architecture checks passed."])
    lines.extend(["", "## Editorial Review", ""])
    lines.extend([f"- {issue}" for issue in editorial_issues] or ["- PASS: editorial checks passed."])
    lines.extend(["", "## Article Snapshot", ""])
    for item in snapshots:
        lines.append(
            f"- {item['source_item_id']}: source={item['source_evidence_count']}, "
            f"local_links={item['local_link_count']}, broken={len(item['broken_local_links'])}, "
            f"todos={item['todo_count']}, nav={'yes' if item['has_series_nav'] else 'no'}"
        )
    return "\n".join(lines).rstrip() + manual_sections


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.topic)
    root = Path(manifest["topic"]["path"])
    prefix = manifest["topic"].get("order_prefix", "S")
    articles = find_articles(manifest["topic"])
    snapshots = [article_snapshot(path, root, prefix) for path in articles]
    report_path = root / "openclaw" / "reviews" / f"{args.date}-daily-review.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    manual_sections = preserve_manual_sections(report_path)
    report_path.write_text(build_report(manifest, snapshots, args.date, manual_sections), encoding="utf-8")

    issue_count = sum(
        1
        for item in snapshots
        for failed in (
            item["source_evidence_count"] < 3,
            bool(item["broken_local_links"]),
            not item["has_series_nav"],
            bool(item["todo_count"]),
        )
        if failed
    )
    verdict = "pass" if issue_count == 0 else "fail"
    print(f"{verdict} (blocking={issue_count}, total={issue_count})")
    print(report_path)
    return 0 if issue_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
