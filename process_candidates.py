#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
ENTRIES_PATH = ROOT / "data" / "entries.json"
CANDIDATES_PATH = ROOT / "data" / "candidates.json"
README_PATH = ROOT / "README.md"

LINK_PRIORITY = (
    "blog",
    "website",
    "url",
    "github",
    "juejin",
    "medium",
    "youtube",
    "newsletter",
    "rss",
    "zhihu",
    "wechat",
    "x",
    "twitter",
)

LINK_ICONS = {
    "blog": "🌐",
    "website": "🌐",
    "url": "🔗",
    "github": "🐙",
    "juejin": "💎",
    "medium": "📝",
    "youtube": "▶️",
    "newsletter": "📬",
    "rss": "📡",
    "zhihu": "💙",
    "wechat": "💬",
    "x": "𝕏",
    "twitter": "𝕏",
    "podcast": "🎙️",
}

CATEGORY_ALIASES = {
    "android": "android-blog",
}


def today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def slug(value: str) -> str:
    value = norm_text(value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value or "source"


def normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.search(r"https?://", raw, re.I):
        if "." not in raw or " " in raw:
            return norm_text(raw)
        raw = "https://" + raw
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+$", "", parsed.path)
    if netloc in {"x.com", "twitter.com"}:
        netloc = "x.com"
        path = path.casefold()
    return urlunparse((scheme, netloc, path, "", "", ""))


def link_values(source: dict[str, Any]) -> dict[str, str]:
    links = source.get("links") or {}
    if not isinstance(links, dict):
        return {}
    return {str(k): str(v).strip() for k, v in links.items() if str(v).strip()}


def normalized_links(source: dict[str, Any]) -> set[str]:
    return {normalize_url(v) for v in link_values(source).values() if normalize_url(v)}


def primary_url(source: dict[str, Any]) -> str:
    links = link_values(source)
    for key in LINK_PRIORITY:
        if key in links:
            return normalize_url(links[key])
    for value in links.values():
        return normalize_url(value)
    return ""


def same_source(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_id = norm_text(left.get("id"))
    right_id = norm_text(right.get("id"))
    if left_id and right_id and left_id == right_id:
        return True
    left_primary = primary_url(left)
    right_primary = primary_url(right)
    if left_primary and right_primary and left_primary == right_primary:
        return True
    return False


def duplicate_reason(candidate: dict[str, Any], entry: dict[str, Any]) -> str | None:
    if norm_text(candidate.get("id")) and norm_text(candidate.get("id")) == norm_text(entry.get("id")):
        return "重复id"
    if norm_text(candidate.get("name")) and norm_text(candidate.get("name")) == norm_text(entry.get("name")):
        return "重复名称"
    candidate_primary = primary_url(candidate)
    entry_primary = primary_url(entry)
    if candidate_primary and entry_primary and candidate_primary == entry_primary:
        return "重复URL"
    candidate_links = normalized_links(candidate)
    entry_links = normalized_links(entry)
    if candidate_links and candidate_links.intersection(entry_links):
        return "重复URL"
    return None


def quality_score(entry: dict[str, Any]) -> tuple[int, int, str]:
    quality = int(entry.get("quality") or 0)
    link_count = len(link_values(entry))
    added = str(entry.get("added_date") or "9999-99-99")
    return quality, link_count, added


def choose_keeper(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_quality, left_links, left_added = quality_score(left)
    right_quality, right_links, right_added = quality_score(right)
    if left_quality != right_quality:
        return left if left_quality > right_quality else right
    if left_links != right_links:
        return left if left_links > right_links else right
    return left if left_added <= right_added else right


def dedupe_entries(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    deduped: list[dict[str, Any]] = []
    removed: list[str] = []
    for entry in entries:
        match_index = next((i for i, existing in enumerate(deduped) if same_source(entry, existing)), None)
        if match_index is None:
            deduped.append(entry)
            continue
        existing = deduped[match_index]
        keeper = choose_keeper(existing, entry)
        loser = entry if keeper is existing else existing
        deduped[match_index] = keeper
        removed.append(f"{loser.get('id') or loser.get('name')}（重复）")
    return deduped, removed


def candidate_decision(candidate: dict[str, Any]) -> tuple[bool, str]:
    quality = int(candidate.get("quality") or 0)
    decision = norm_text(candidate.get("decision") or candidate.get("final_decision"))
    if quality <= 2:
        return False, "quality≤2"
    if quality >= 4:
        return True, ""
    if quality == 3 and decision in {"accept", "accepted", "true", "yes", "收录"}:
        return True, ""
    return False, "quality=3未显式收录"


def entry_from_candidate(candidate: dict[str, Any], added_date: str) -> dict[str, Any]:
    name = str(candidate.get("name") or candidate.get("author") or "Unnamed").strip()
    category = normalize_category(candidate.get("category"))
    links = link_values(candidate)
    candidate_id = str(candidate.get("id") or f"{slug(name)}-{slug(category)}").strip()
    return {
        "id": candidate_id,
        "name": name,
        "category": category,
        "author": str(candidate.get("author") or name).strip(),
        "desc": str(candidate.get("desc") or candidate.get("summary") or "").strip(),
        "links": links,
        "tags": [str(tag).strip() for tag in candidate.get("tags", []) if str(tag).strip()],
        "quality": int(candidate.get("quality") or 0),
        "added_date": added_date,
    }


def normalize_category(value: Any) -> str:
    raw = str(value or "general-tech").strip() or "general-tech"
    return CATEGORY_ALIASES.get(raw, raw)


def process_candidates() -> tuple[int, int, int, list[str], list[str], list[str], int]:
    run_date = today()
    candidates_data = load_json(CANDIDATES_PATH)
    entries_data = load_json(ENTRIES_PATH)
    entries = entries_data.get("entries")
    candidates = candidates_data.get("candidates")
    if not isinstance(entries, list):
        raise ValueError("data/entries.json must contain an entries array")
    if not isinstance(candidates, list):
        raise ValueError("data/candidates.json must contain a candidates array")

    for entry in entries:
        entry["category"] = normalize_category(entry.get("category"))
    entries, removed_duplicates = dedupe_entries(entries)
    accepted_names: list[str] = []
    skipped_names: list[str] = []
    errors: list[str] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("候选结构不是对象")
            continue
        candidate_name = str(candidate.get("name") or candidate.get("id") or "unnamed").strip()
        try:
            existing = next((entry for entry in entries if duplicate_reason(candidate, entry)), None)
            if existing:
                skipped_names.append(f"{candidate_name}（{duplicate_reason(candidate, existing)}）")
                continue
            should_accept, reason = candidate_decision(candidate)
            if not should_accept:
                skipped_names.append(f"{candidate_name}（{reason}）")
                continue
            entries.insert(0, entry_from_candidate(candidate, run_date))
            accepted_names.append(candidate_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate_name}（{exc}）")

    entries_data["entries"] = entries
    entries_data["updated"] = run_date
    candidates_data["processed_count"] = int(candidates_data.get("processed_count") or 0) + len(candidates)
    candidates_data["processed_date"] = run_date if candidates else candidates_data.get("processed_date", run_date)
    candidates_data["candidates"] = []
    candidates_data["new_candidates"] = 0

    save_json(ENTRIES_PATH, entries_data)
    save_json(CANDIDATES_PATH, candidates_data)
    generate_readme(entries_data)

    return (
        len(accepted_names),
        len(skipped_names),
        len(errors),
        accepted_names,
        skipped_names,
        removed_duplicates,
        len(entries),
    )


def safe(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def link_markdown(links: dict[str, str]) -> str:
    parts: list[str] = []
    for key, value in links.items():
        icon = LINK_ICONS.get(key, "🔗")
        if re.search(r"^https?://", value, re.I):
            parts.append(f"[{icon}]({value})")
        else:
            parts.append(f"[{icon}]({value})")
    return " ".join(parts)


def category_label(category_id: str, categories: dict[str, dict[str, Any]]) -> str:
    category = categories.get(category_id) or {}
    return str(category.get("name") or category_id)


def anchor(category_id: str) -> str:
    return re.sub(r"[^a-z0-9]", "", category_id.lower())


def generate_readme(entries_data: dict[str, Any]) -> None:
    entries = entries_data["entries"]
    categories_list = entries_data.get("categories", [])
    categories = {c["id"]: c for c in categories_list if isinstance(c, dict) and "id" in c}
    count = len(entries)
    updated = entries_data.get("updated") or today()

    entries_by_category: dict[str, list[dict[str, Any]]] = {cid: [] for cid in categories}
    for entry in entries:
        entries_by_category.setdefault(str(entry.get("category") or "general-tech"), []).append(entry)

    recent = sorted(
        entries,
        key=lambda e: str(e.get("added_date") or ""),
        reverse=True,
    )[:10]

    lines = [
        "# Awesome Android AI Dev Sources",
        "",
        f"![GitHub stars](https://img.shields.io/github/stars/Gracker/awesome-android-ai-dev-sources?style=social) ![GitHub last commit](https://img.shields.io/github/last-commit/Gracker/awesome-android-ai-dev-sources) ![License](https://img.shields.io/github/license/Gracker/awesome-android-ai-dev-sources) ![Sources](https://img.shields.io/badge/信息源-{count}-blue)",
        "",
        f"> {entries_data.get('description', '开发者高质量信息源导航')}",
        "",
        "## 👤 关于作者",
        "",
        "| | |",
        "|-|-|",
        "| **博客** | [androidperformance.com](https://www.androidperformance.com/) — Android 性能优化技术博客，专注启动、内存、功耗、滑动 |",
        "| **Android Weekly** | [androidPerformance.cn](https://androidPerformance.cn) — 每周精选全球 Android 最佳文章 |",
        "| **知乎** | [@Gracker](https://www.zhihu.com/people/gracker) |",
        "| **即刻** | [@Gracker](https://okjk.co/pJbjFa) |",
        "| **公众号** | AndroidPerformance |",
        "| **掘金** | [@Gracker](https://juejin.cn/user/1816846860560749) |",
        "| **微信** | 553000664（星球/群相关） |",
        "",
        "**快速导航**",
        " · ".join(f"[{safe(category_label(cid, categories))}](#{anchor(cid)})" for cid in entries_by_category),
        "",
        "---",
        "",
        "## 🔥 最近收录",
        f"> 每日自动发现，LLM 评估后收录 · 更新于 {updated}",
        "",
        "| 信息源 | 领域 | 描述 |",
        "|--------|------|------|",
    ]

    for entry in recent:
        links = link_markdown(link_values(entry))
        category = category_label(str(entry.get("category") or ""), categories)
        lines.append(f"| **{safe(entry.get('name'))}** {links} | {safe(category)} | {safe(entry.get('desc'))} |")

    for category_id, category_entries in entries_by_category.items():
        if not category_entries:
            continue
        category = categories.get(category_id, {"name": category_id, "desc": ""})
        lines.extend(
            [
                "",
                f'<a id="{anchor(category_id)}"></a>',
                f"## {safe(category.get('name') or category_id)}",
                f"*{safe(category.get('desc'))}* · {len(category_entries)} 个源",
                "",
                "| 信息源 | 描述 |",
                "|--------|------|",
            ]
        )
        for entry in category_entries:
            links = link_markdown(link_values(entry))
            lines.append(f"| **{safe(entry.get('name'))}** {links} | {safe(entry.get('desc'))} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 自动化说明",
            "",
            "- Dev-Radar 每日发现任务写入 `data/candidates.json`。",
            "- Dev-Radar 自动收录任务运行 `python3 process_candidates.py`，统一处理去重、收录、README 更新和统计输出。",
            "- `data/entries.json` 是源列表的结构化事实来源。",
        ]
    )

    README_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    accepted, skipped, errors, accepted_names, skipped_names, removed, total_sources = process_candidates()
    print(f"📥 Dev-Radar 自动收录 · {today()}")
    print(f"收录 {accepted} 个，跳过 {skipped} 个，异常 {errors} 个")
    print(f"新收录：{'、'.join(accepted_names) if accepted_names else '无'}")
    print(f"跳过：{'、'.join(skipped_names) if skipped_names else '无'}")
    if removed:
        print(f"清理重复：{'、'.join(removed)}")
    print(f"总计 {total_sources} 个源")
