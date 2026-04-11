#!/usr/bin/env python3
"""Generate README.md from data/entries.json.

Usage:
    python3 scripts/generate-readme.py           # writes README.md
    python3 scripts/generate-readme.py --check   # dry-run, prints stats only
"""

import json
import os
import sys

LINK_ICONS = {
    "blog": "🌐",
    "website": "🔗",
    "rss": "📡",
    "x": "𝕏",
    "youtube": "▶️",
    "github": "🐙",
    "zhihu": "💙",
    "juejin": "💎",
    "wechat": "💬",
    "medium": "📝",
    "telegram": "✈️",
    "newsletter": "📬",
    "podcast": "🎙️",
}

LINK_ORDER = [
    "blog", "website", "rss", "x", "youtube", "github",
    "zhihu", "juejin", "wechat", "medium", "telegram",
    "newsletter", "podcast",
]

FIELD_LABELS = {
    "android-official": "Android",
    "android-blog": "Android",
    "android-community": "Android",
    "ai": "AI",
    "general-tech": "通用",
    "tools": "工具",
}


def load_data():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "entries.json")
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_links_inline(links):
    parts = []
    for key in LINK_ORDER:
        url = links.get(key)
        if url:
            icon = LINK_ICONS.get(key, "🔗")
            parts.append(f"[{icon}]({url})")
    if not parts:
        return ""
    return " " + " ".join(parts)


def render_stars(quality):
    return "⭐" * quality + "☆" * (5 - quality)


def generate(data, check=False):
    categories = data["categories"]
    entries = data["entries"]
    name = data["name"]
    description = data["description"]
    updated = data["updated"]

    # Group entries by category, sort by quality desc
    grouped = {}
    for cat in categories:
        grouped[cat["id"]] = []
    for entry in entries:
        grouped.setdefault(entry["category"], []).append(entry)
    for cat_id in grouped:
        grouped[cat_id].sort(key=lambda e: e.get("quality", 3), reverse=True)

    total_entries = len(entries)
    total_categories = len(categories)

    lines = []

    # ===== Header =====
    lines.append(f"# {name}")
    lines.append("")
    lines.append(
        f"![GitHub stars](https://img.shields.io/github/stars/Gracker/awesome-android-ai-dev-sources?style=social) "
        f"![GitHub last commit](https://img.shields.io/github/last-commit/Gracker/awesome-android-ai-dev-sources) "
        f"![License](https://img.shields.io/github/license/Gracker/awesome-android-ai-dev-sources) "
        f"![Sources](https://img.shields.io/badge/信息源-{total_entries}-blue)"
    )
    lines.append("")
    lines.append(f"> {description}")
    lines.append("")

    # ===== About the Author =====
    lines.append("## 👤 关于作者")
    lines.append("")
    lines.append("| | |")
    lines.append("|-|-|")
    lines.append("| **博客** | [androidperformance.com](https://www.androidperformance.com/) — Android 性能优化技术博客，专注启动、内存、功耗、滑动 |")
    lines.append("| **Android Weekly** | [androidPerformance.cn](https://androidPerformance.cn) — 每周精选全球 Android 最佳文章 |")
    lines.append("| **知乎** | [@Gracker](https://www.zhihu.com/people/gracker) |")
    lines.append("| **即刻** | [@Gracker](https://okjk.co/pJbjFa) |")
    lines.append("| **公众号** | AndroidPerformance |")
    lines.append("| **掘金** | [@Gracker](https://juejin.cn/user/1816846860560749) |")
    lines.append("| **微信** | 553000664（星球/群相关） |")
    lines.append("")
    lines.append("### 🌟 知识星球")
    lines.append("")
    lines.append("**特色服务：1v1 线上看 Trace / 学习 Trace 分析**")
    lines.append("")
    lines.append("- **平台**：腾讯视频 | **内容**：聚焦看 Trace，可自备 Trace 或现场抓")
    lines.append("- **预约时间**：周末晚 9:00 后 / 工作日晚 10:00 后（微信提前约）")
    lines.append("- **星球微信群**：仅限星球成员，讨论 Android 性能优化、Framework、Linux、大前端、面试等技术话题")
    lines.append("- **群满/二维码失效**：加微信 553000664 拉群")
    lines.append("")

    # ===== Quick Nav =====
    lines.append("**快速导航**")
    nav_parts = []
    for cat in categories:
        nav_parts.append(f"[{cat['name']}](#{cat['id'].replace('-', '')})")
    nav_parts.append("[📚 推荐资源](#推荐资源)")
    nav_parts.append("[📡 订阅](#订阅)")
    lines.append(" · ".join(nav_parts))
    lines.append("")
    lines.append("---")

    # ===== Recommended Resources =====
    lines.append("")
    lines.append('<a id="推荐资源"></a>')
    lines.append("## 📚 推荐资源")
    lines.append("")
    lines.append("### 📖 书籍")
    lines.append("")
    lines.append("| 书名 | 说明 |")
    lines.append("|------|------|")
    lines.append("| [Android性能优化之道 + Android系统性能优化（套装）](https://item.jd.com/10143552877886.html) | 赵子健《性能优化之道》偏 App 优化；中兴团队《系统性能优化》偏系统层面 |")
    lines.append("| [性能之巅（第2版）：系统、企业与云可观测性](https://item.jd.com/13199661.html) | 大部头宝典，偏 Linux，可当参考书 |")
    lines.append("")
    lines.append("### 🎓 在线课程")
    lines.append("")
    lines.append("| 课程 | 说明 |")
    lines.append("|------|------|")
    lines.append("| [Pika · Android 应用稳定性剖析与优化](https://juejin.cn/book/7280546228559151162) | 掘金专栏，查漏补缺 |")
    lines.append("| [赵子健 · Android 性能优化](https://juejin.cn/book/7153836660768292878) | 掘金专栏，体系化学习 |")
    lines.append("")
    lines.append("### 🎬 推荐关注")
    lines.append("")
    lines.append("| 名称 | 平台 | 说明 |")
    lines.append("|------|------|------|")
    lines.append("| [赵俊民](https://www.zhihu.com/people/zhao-jun-min-80) | 知乎 | 很多系统优化方面的思考和文章 |")
    lines.append("| [王小二的技术栈](https://space.bilibili.com/485954104) | B站 | 很多系统原理方面的视频 |")
    lines.append("| [千里马学框架](https://space.bilibili.com/397723494) | B站 | 专门教 Framework 开发 |")
    lines.append("| [掘金](https://juejin.cn/) | 网站 | 搜索技术问题可优先看掘金 |")
    lines.append("")
    lines.append("### 🔧 学习建议")
    lines.append("")
    lines.append("**Perfetto / Systrace 学习路径**（参考 [博客系列](https://www.androidperformance.com/2019/12/01/BlogMap/)）：")
    lines.append("")
    lines.append("1. 找一个场景，抓 Trace")
    lines.append("2. 打开 Trace + [Perfetto 官方文档](https://perfetto.dev/docs/) + AOSP 源码（[cs.android.com](https://cs.android.com)）")
    lines.append("3. 对着 Trace + 博客文章 + AOSP 源码，梳理主要流程")
    lines.append("4. 记笔记，搞清楚 Trace 上每一个 Tag 的含义")
    lines.append("5. 遇到问题：提供上下文给 AI / 星球提问 / 微信找我")
    lines.append("")

    # ===== Recent entries (top 10 by added_date) =====
    recent = sorted(
        [e for e in entries if e.get("added_date")],
        key=lambda e: e.get("added_date", ""),
        reverse=True,
    )[:10]

    if recent:
        lines.append("---")
        lines.append("")
        lines.append("## 🔥 最近收录")
        lines.append("> 每日自动发现，LLM 评估后收录 · 更新于 " + updated)
        lines.append("")
        lines.append("| 信息源 | 领域 | 描述 |")
        lines.append("|--------|------|------|")
        for entry in recent:
            link_str = render_links_inline(entry.get("links", {}))
            stars = render_stars(entry.get("quality", 3))
            field = FIELD_LABELS.get(entry["category"], entry["category"])
            name_col = f"**{entry['name']}**{link_str}"
            desc_col = f"{entry['desc']} {stars}"
            lines.append(f"| {name_col} | {field} | {desc_col} |")
        lines.append("")

    # ===== Categories =====
    for cat in categories:
        cat_entries = grouped.get(cat["id"], [])
        anchor = cat["id"].replace("-", "")
        lines.append("")
        lines.append(f'<a id="{anchor}"></a>')
        lines.append(f"## {cat['name']}")
        lines.append(f"*{cat['desc']}* · {len(cat_entries)} 个源")
        lines.append("")

        lines.append("| 信息源 | 描述 |")
        lines.append("|--------|------|")
        for entry in cat_entries:
            link_str = render_links_inline(entry.get("links", {}))
            stars = render_stars(entry.get("quality", 3))
            name_col = f"**{entry['name']}**{link_str}"
            desc_col = f"{entry['desc']} {stars}"
            lines.append(f"| {name_col} | {desc_col} |")

        if cat["id"] == "ai":
            lines.append("")
            lines.append(
                "> 📌 更多 AI 资源见 "
                "[awesome-ai-field-notes](https://github.com/Gracker/awesome-ai-field-notes)"
                "（608 条，每日更新）"
            )

    # ===== Footer =====
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append('<a id="订阅"></a>')
    lines.append("## 📋 贡献指南")
    lines.append("")
    lines.append("1. Fork 本仓库")
    lines.append("2. 编辑 `data/entries.json`，按 schema 添加新条目")
    lines.append("3. 运行 `python3 scripts/generate-readme.py` 重新生成 README")
    lines.append("4. 运行 `python3 scripts/check-links.py` 验证链接")
    lines.append("5. 提交 PR")
    lines.append("")
    lines.append("### 📡 订阅")
    lines.append("")
    lines.append("- [OPML 文件](data/feeds.opml) — 导入到 RSS 阅读器（Inoreader、Feedly、Follow 等）")
    lines.append("")
    lines.append("### 自动维护")
    lines.append("")
    lines.append("- 每日发现任务由 [OpenClaw](https://github.com/openclaw/openclaw) 自动执行")
    lines.append("- 扫描 Android Weekly、掘金、GitHub Trending、RSS 列表、Obsidian 产出")
    lines.append("- LLM 评估后自动收录，README + OPML 每日更新")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f'<p align="center">Licensed under the terms of the <a href="https://github.com/Gracker/awesome-android-ai-dev-sources/blob/main/LICENSE">LICENSE</a> file.</p>')

    readme = "\n".join(lines) + "\n"

    if check:
        print(f"README would contain {len(readme)} chars, {total_entries} entries, {total_categories} categories")
        return readme

    readme_path = os.path.join(os.path.dirname(__file__), "..", "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    print(f"README.md generated ({len(readme)} chars, {total_entries} entries, {total_categories} categories)")
    return readme


if __name__ == "__main__":
    data = load_data()
    check = "--check" in sys.argv
    generate(data, check=check)
