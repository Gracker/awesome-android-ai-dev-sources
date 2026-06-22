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

README_MIN_QUALITY = 4
README_DURABLE_LINK_KEYS = set(LINK_PRIORITY) | {"podcast"}
README_TRANSIENT_CONTENT_TYPES = {
    "article",
    "daily",
    "news",
    "news-event",
    "post",
    "single-article",
    "single-post",
    "single-tweet",
    "single-video",
    "thread",
    "tweet",
    "video",
}
README_TRUE_VALUES = {"1", "true", "yes", "y", "on", "accept", "accepted", "收录", "是"}
README_FALSE_VALUES = {"0", "false", "no", "n", "off", "reject", "rejected", "跳过", "否"}


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


def bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = norm_text(value)
    if normalized in README_TRUE_VALUES:
        return True
    if normalized in README_FALSE_VALUES:
        return False
    return None


def readme_override(source: dict[str, Any]) -> bool | None:
    readme = source.get("readme")
    if isinstance(readme, dict) and "eligible" in readme:
        parsed = bool_value(readme.get("eligible"))
        if parsed is not None:
            return parsed
    elif readme is not None:
        parsed = bool_value(readme)
        if parsed is not None:
            return parsed

    for key in ("readme_eligible", "update_readme", "readme_update"):
        if key in source:
            parsed = bool_value(source.get(key))
            if parsed is not None:
                return parsed
    return None


def link_values(source: dict[str, Any]) -> dict[str, str]:
    links = source.get("links") or {}
    if not isinstance(links, dict):
        return {}
    return {str(k): str(v).strip() for k, v in links.items() if str(v).strip()}


def normalized_links(source: dict[str, Any]) -> set[str]:
    return {normalize_url(v) for v in link_values(source).values() if normalize_url(v)}


def transient_link(key: str, value: str) -> bool:
    normalized = normalize_url(value)
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]

    if not host:
        return False
    if host == "x.com":
        return len(parts) >= 3 and parts[1] in {"status", "statuses"}
    if host == "github.com":
        return len(parts) >= 3 and parts[2] in {"blob", "commit", "commits", "discussions", "issues", "pull", "releases", "tree"}
    if host == "juejin.cn":
        return bool(parts) and parts[0] in {"book", "pin", "post", "video"}
    if host == "zhihu.com":
        return bool(parts) and parts[0] in {"answer", "pin", "question", "zvideo"}
    if host in {"youtube.com", "m.youtube.com", "www.youtube.com", "youtu.be"}:
        return host == "youtu.be" or (bool(parts) and parts[0] in {"clip", "shorts", "watch"})
    if host == "medium.com":
        return len(parts) > 1
    if host == "mp.weixin.qq.com":
        return bool(parts) and parts[0] in {"s", "mp"}
    if host.endswith(".substack.com"):
        return bool(parts) and parts[0] in {"p", "i"}
    if key in {"blog", "newsletter", "url", "website"}:
        if len(parts) >= 2 and parts[0] in {"article", "articles", "blog", "news", "post", "posts"}:
            return True
        if len(parts) >= 3 and re.fullmatch(r"20\d{2}", parts[0]) and re.fullmatch(r"\d{1,2}", parts[1]):
            return True
    if key in {"x", "twitter"}:
        return len(parts) >= 3 and parts[1] in {"status", "statuses"}
    return False


def stable_readme_link(source: dict[str, Any]) -> bool:
    for key, value in link_values(source).items():
        if key not in README_DURABLE_LINK_KEYS:
            continue
        if normalize_url(value) and not transient_link(key, value):
            return True
    return False


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


def readme_update_decision(source: dict[str, Any], category_ids: set[str]) -> tuple[bool, str]:
    override = readme_override(source)
    if override is False:
        return False, "readme_eligible=false"

    name = norm_text(source.get("name") or source.get("author"))
    if not name:
        return False, "缺少名称"
    category = normalize_category(source.get("category"))
    if category not in category_ids:
        return False, "未知分类"
    if not link_values(source):
        return False, "缺少链接"
    if not stable_readme_link(source):
        return False, "只有单条内容链接"
    if not norm_text(source.get("desc") or source.get("summary")):
        return False, "缺少源级描述"

    content_type = norm_text(source.get("content_type") or source.get("type") or source.get("source_type"))
    if content_type in README_TRANSIENT_CONTENT_TYPES:
        return False, "单条内容不是长期源"

    quality = int(source.get("quality") or 0)
    if quality < README_MIN_QUALITY:
        return False, f"quality<{README_MIN_QUALITY}"

    return True, "长期信息源"


def entry_from_candidate(candidate: dict[str, Any], added_date: str, readme_reason: str) -> dict[str, Any]:
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
        "readme": {
            "eligible": True,
            "reason": readme_reason,
        },
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
    category_ids = {str(category.get("id")) for category in entries_data.get("categories", []) if isinstance(category, dict)}
    accepted_names: list[str] = []
    skipped_names: list[str] = []
    errors: list[str] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("候选结构不是对象")
            continue
        candidate_name = str(candidate.get("name") or candidate.get("id") or "unnamed").strip()
        try:
            existing_match = next(
                ((i, entry, duplicate_reason(candidate, entry)) for i, entry in enumerate(entries) if duplicate_reason(candidate, entry)),
                None,
            )
            if existing_match:
                _, existing, duplicate = existing_match
                existing_readme_ok, _ = readme_update_decision(existing, category_ids)
                if existing_readme_ok:
                    skipped_names.append(f"{candidate_name}（{duplicate}）")
                    continue
            should_accept, reason = candidate_decision(candidate)
            if not should_accept:
                skipped_names.append(f"{candidate_name}（{reason}）")
                continue
            readme_ok, readme_reason = readme_update_decision(candidate, category_ids)
            if not readme_ok:
                skipped_names.append(f"{candidate_name}（不更新README：{readme_reason}）")
                continue
            new_entry = entry_from_candidate(candidate, run_date, readme_reason)
            if existing_match:
                index, _, duplicate = existing_match
                entries[index] = new_entry
                accepted_names.append(f"{candidate_name}（升级{duplicate}）")
                continue
            entries.insert(0, new_entry)
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
        url = markdown_url(value)
        if url:
            parts.append(f"[{icon}]({url})")
        else:
            parts.append(f"{icon} {safe(value)}")
    return " ".join(parts)


def markdown_url(value: str) -> str:
    raw = str(value or "").strip()
    if re.search(r"^https?://", raw, re.I):
        return raw
    if "." in raw and " " not in raw and not re.search(r"[\u4e00-\u9fff]", raw):
        return "https://" + raw
    return ""


def category_label(category_id: str, categories: dict[str, dict[str, Any]]) -> str:
    category = categories.get(category_id) or {}
    return str(category.get("name") or category_id)


def anchor(category_id: str) -> str:
    return re.sub(r"[^a-z0-9]", "", category_id.lower())


def entry_visible_in_readme(entry: dict[str, Any], category_ids: set[str]) -> bool:
    eligible, _ = readme_update_decision(entry, category_ids)
    return eligible


def readme_source_count(entries_data: dict[str, Any]) -> int:
    category_ids = {str(category.get("id")) for category in entries_data.get("categories", []) if isinstance(category, dict)}
    return sum(
        1
        for entry in entries_data.get("entries", [])
        if isinstance(entry, dict) and entry_visible_in_readme(entry, category_ids)
    )


def generate_readme(entries_data: dict[str, Any]) -> None:
    entries = entries_data["entries"]
    categories_list = entries_data.get("categories", [])
    categories = {c["id"]: c for c in categories_list if isinstance(c, dict) and "id" in c}
    category_ids = set(categories)
    readme_entries = [entry for entry in entries if entry_visible_in_readme(entry, category_ids)]
    count = len(readme_entries)
    updated = entries_data.get("updated") or today()

    entries_by_category: dict[str, list[dict[str, Any]]] = {cid: [] for cid in categories}
    for entry in readme_entries:
        entries_by_category.setdefault(str(entry.get("category") or "general-tech"), []).append(entry)

    recent = sorted(
        readme_entries,
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
            "- Dev-Radar 自动收录任务运行 `python3 process_candidates.py`，统一处理去重、收录、README eligibility、README 更新和统计输出。",
            f"- README 只展示长期信息源：稳定主页/profile/repo/feed、已知分类、源级描述、quality≥{README_MIN_QUALITY}；单篇文章、单条 tweet、新闻事件和临时链接不会更新 README。",
            "- README badge 统计的是通过 eligibility gate 的展示源数量；`data/entries.json` 保留结构化源数据。",
            "- `data/entries.json` 是源列表的结构化事实来源。",
        ]
    )

    README_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    accepted, skipped, errors, accepted_names, skipped_names, removed, total_sources = process_candidates()
    readme_sources = readme_source_count(load_json(ENTRIES_PATH))
    print(f"📥 Dev-Radar 自动收录 · {today()}")
    print(f"收录 {accepted} 个，跳过 {skipped} 个，异常 {errors} 个")
    print(f"新收录：{'、'.join(accepted_names) if accepted_names else '无'}")
    print(f"跳过：{'、'.join(skipped_names) if skipped_names else '无'}")
    if removed:
        print(f"清理重复：{'、'.join(removed)}")
    print(f"总计 {total_sources} 个源，README 展示 {readme_sources} 个源")
