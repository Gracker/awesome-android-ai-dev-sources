#!/usr/bin/env python3
"""Read-only monitor for Feishu daily sync outputs.

This script is intentionally local-only: it reads generated reports, does not
load credential files, and never calls the Feishu API.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "generated" / "daily"

BLOCKING_KEYWORDS = (
    "blocked",
    "duplicate path",
    "duplicate_paths",
    "source discovery",
    "stale_baseline",
    "unpublished_current",
    "needs_secret",
    "running_or_stale",
    "locked",
    "catchup_blocked",
    "write_blocked",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Monitor latest Feishu daily sync outputs")
    parser.add_argument("--date", help="Date directory to inspect, in YYYY-MM-DD format")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the latest sync status is not ok",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit only the machine-readable JSON summary",
    )
    return parser.parse_args()


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def latest_report_dir():
    if not DAILY_DIR.exists():
        return None
    candidates = [
        path
        for path in DAILY_DIR.iterdir()
        if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.name)[-1]


def count_items(report):
    summary = report.get("summary")
    if isinstance(summary, dict):
        return {
            "create": int(summary.get("create") or 0),
            "update": int(summary.get("update") or 0),
            "skip": int(summary.get("skip") or 0),
            "error": int(summary.get("error") or 0),
        }

    article_count = int(report.get("article_count") or 0)
    if "review_verdict" in report:
        # The lightweight local cron wrapper models the reviewed daily series as
        # the changed set, because it does not have per-document create/update
        # planning data.
        return {
            "create": 0,
            "update": article_count,
            "skip": 0,
            "error": 0,
        }

    return {
        "create": int(report.get("create") or 0),
        "update": int(report.get("update") or 0),
        "skip": int(report.get("skip") or 0),
        "error": int(report.get("error") or 0),
    }

    return {
        "create": int(report.get("create") or 0),
        "update": int(report.get("update") or 0),
        "skip": int(report.get("skip") or 0),
        "error": int(report.get("error") or 0),
    }


def gate_from_reports(report, sanity=None):
    reasons = []

    if sanity is not None:
        if sanity.get("passed") is True:
            gate = "pass"
        else:
            gate = "fail"
            reasons.append("sanity gate failed")

        errors = sanity.get("errors")
        if isinstance(errors, list) and errors:
            reasons.extend(str(error) for error in errors)

        duplicate_paths = int(sanity.get("duplicate_paths") or 0)
        if duplicate_paths:
            reasons.append(f"duplicate_paths={duplicate_paths}")

        conversion_errors = int(sanity.get("conversion_errors") or 0)
        if conversion_errors:
            reasons.append(f"conversion_errors={conversion_errors}")

        return gate, reasons

    verdict = str(report.get("review_verdict") or "").strip().lower()
    if verdict:
        if verdict == "pass":
            return "pass", reasons
        reasons.append(f"review_verdict={verdict}")
        return "fail", reasons

    return "unknown", reasons


def find_blocking_text(*texts):
    joined = "\n".join(texts).lower()
    found = []
    for keyword in BLOCKING_KEYWORDS:
        if keyword in joined:
            found.append(keyword)
    return found


def owner_report_for(out_dir, report):
    owner_report = out_dir / "owner-report.md"
    if owner_report.exists():
        return str(owner_report)

    review_report = report.get("review_report")
    if isinstance(review_report, str) and review_report:
        return review_report

    sync_report = out_dir / "sync-report.md"
    if sync_report.exists():
        return str(sync_report)

    return str(out_dir)


def inspect_aiw_safety(out_dir: Path) -> dict[str, Any]:
    """Read AIW safety artifacts and flag map/Unmapped regressions."""
    safety_path = out_dir / "aiw-safety.json"
    report_path = out_dir / "sync-report.json"
    sources_path = ROOT / "config" / "sources.json"
    result: dict[str, Any] = {
        "map_entries": None,
        "aiw_unmapped": None,
        "aiw_upserts": None,
        "source_path_ok": None,
        "errors": [],
    }

    safety = None
    if safety_path.exists():
        safety = load_json(safety_path)
    elif report_path.exists():
        report = load_json(report_path)
        if isinstance(report.get("aiw_safety"), dict):
            safety = report["aiw_safety"]

    if isinstance(safety, dict):
        result["map_entries"] = safety.get("map_entries")
        result["aiw_unmapped"] = safety.get("aiw_unmapped")
        result["aiw_upserts"] = safety.get("aiw_upserts")
        errs = safety.get("errors") or []
        if isinstance(errs, list):
            result["errors"].extend(str(e) for e in errs)

    if sources_path.exists():
        try:
            cfg = load_json(sources_path)
            aiw = next((s for s in (cfg.get("sources") or []) if s.get("id") == "aiw"), None)
            path = str((aiw or {}).get("path") or "")
            result["source_path"] = path
            ok = "work-copies/Android-Internal-Wiki" in path
            result["source_path_ok"] = ok
            if not ok:
                result["errors"].append("AIW source path is not GitHub work-copy")
        except Exception as exc:
            result["errors"].append(f"sources.json read failed: {exc}")

    if result["map_entries"] is not None and int(result["map_entries"] or 0) < 100:
        result["errors"].append(f"aiw-map too small: {result['map_entries']}")
    if result["aiw_unmapped"] is not None and int(result["aiw_unmapped"] or 0) > 0:
        result["errors"].append(f"aiw_unmapped={result['aiw_unmapped']}")

    # Fallback: inspect publish-plan if safety file missing.
    plan_path = out_dir / "publish-plan.json"
    if result["aiw_unmapped"] is None and plan_path.exists():
        try:
            plan = load_json(plan_path)
            ops = plan.get("operations") or []
            unmapped = 0
            upserts = 0
            for op in ops:
                if op.get("operation") != "upsert_document" or op.get("source_id") != "aiw":
                    continue
                upserts += 1
                wp = op.get("wiki_path") or []
                if "Unmapped" in wp:
                    unmapped += 1
            result["aiw_upserts"] = upserts
            result["aiw_unmapped"] = unmapped
            if unmapped:
                result["errors"].append(f"publish-plan aiw_unmapped={unmapped}")
        except Exception:
            pass

    result["ok"] = not result["errors"]
    return result


def inspect_non_aiw_health(out_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Guard non-AIW sources: stale state, empty active sources, and leaked work materials."""
    result: dict[str, Any] = {
        "retired_documents": 0,
        "retired_by_source": {},
        "empty_active_sources": [],
        "suspicious_counts": {},
        "duplicate_title_groups": 0,
        "errors": [],
    }
    items = report.get("items") or []
    if not isinstance(items, list):
        items = []
    current = {
        (str(item.get("source_id") or ""), str(item.get("source_item_id") or ""))
        for item in items
        if isinstance(item, dict)
    }

    sources_path = ROOT / "config" / "sources.json"
    if sources_path.exists():
        try:
            cfg = load_json(sources_path)
            active_sources = [str(s.get("id") or "") for s in (cfg.get("sources") or []) if isinstance(s, dict)]
            counts = {sid: 0 for sid in active_sources}
            for sid, _ in current:
                if sid in counts:
                    counts[sid] += 1
            # A configured source with zero current markdown is usually a stale source config.
            for sid, count in counts.items():
                if sid and count == 0:
                    result["empty_active_sources"].append(sid)
            if result["empty_active_sources"]:
                result["errors"].append("empty_active_sources=" + ",".join(result["empty_active_sources"]))
        except Exception as exc:
            result["errors"].append(f"sources.json non-aiw check failed: {exc}")

    state_path = ROOT / "registry" / "publish-state.json"
    if state_path.exists():
        try:
            state = load_json(state_path)
            docs = state.get("documents") or {}
            retired_by_source: dict[str, int] = {}
            retired = 0
            for key in docs.keys():
                key_s = str(key)
                if "/" not in key_s:
                    continue
                sid, item_id = key_s.split("/", 1)
                if sid == "aiw":
                    continue
                if (sid, item_id) not in current:
                    retired += 1
                    retired_by_source[sid] = retired_by_source.get(sid, 0) + 1
            result["retired_documents"] = retired
            result["retired_by_source"] = retired_by_source
            if retired:
                parts = [f"{sid}:{count}" for sid, count in sorted(retired_by_source.items())]
                result["errors"].append("non_aiw_retired_documents=" + ",".join(parts))
        except Exception as exc:
            result["errors"].append(f"publish-state non-aiw check failed: {exc}")

    suspicious_patterns = {
        "raw": lambda item_id: "/raw/" in item_id,
        "references": lambda item_id: "/references/" in item_id,
        "gracker_diagrams": lambda item_id: "gracker-diagrams/" in item_id,
        "diagram": lambda item_id: "/diagram/" in item_id,
        "local_context": lambda item_id: item_id.endswith("/00-local-context.md") or item_id == "00-local-context.md",
        "status": lambda item_id: item_id.endswith("/STATUS.md") or item_id == "STATUS.md",
        "copy_md": lambda item_id: item_id.endswith("/copy.md") or item_id == "copy.md",
        "prompts": lambda item_id: "/prompts/" in item_id,
        "shell_template_date": lambda item_id: "$(date" in item_id,
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id") or "")
        if not sid or sid == "aiw":
            continue
        item_id = str(item.get("source_item_id") or "")
        for name, predicate in suspicious_patterns.items():
            if predicate(item_id):
                result["suspicious_counts"][name] = result["suspicious_counts"].get(name, 0) + 1
    if result["suspicious_counts"]:
        parts = [f"{name}:{count}" for name, count in sorted(result["suspicious_counts"].items())]
        result["errors"].append("suspicious_non_aiw_paths=" + ",".join(parts))

    seen: dict[tuple[str, str], int] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("source_id") == "aiw":
            continue
        key = (str(item.get("category") or ""), str(item.get("title") or ""))
        seen[key] = seen.get(key, 0) + 1
    result["duplicate_title_groups"] = sum(1 for count in seen.values() if count > 1)
    result["ok"] = not result["errors"]
    return result


def inspect_date(out_dir):
    report_path = out_dir / "sync-report.json"
    sync_report_md = out_dir / "sync-report.md"
    sanity_path = out_dir / "sanity-gate.json"
    owner_report_path = out_dir / "owner-report.md"

    if not report_path.exists():
        return {
            "status": "error",
            "gate": "missing_report",
            "date": out_dir.name,
            "create": 0,
            "update": 0,
            "skip": 0,
            "error": 1,
            "changed_items": 0,
            "credential_env": "not_checked",
            "latest_runs": f"{out_dir.name}: sync-report.json missing",
            "owner_report": str(out_dir),
            "sync_report": str(report_path),
            "manual_intervention": "sync-report.json missing",
            "aiw_safety": {"ok": False, "errors": ["missing report"]},
        }

    report = load_json(report_path)
    sanity = load_json(sanity_path) if sanity_path.exists() else None
    counts = count_items(report)
    gate, reasons = gate_from_reports(report, sanity)
    aiw_safety = inspect_aiw_safety(out_dir)
    non_aiw_health = inspect_non_aiw_health(out_dir, report)

    # If the structured sanity gate already passed, trust it. Keyword scanning the
    # full report body causes false positives on fields like "duplicate_paths": 0
    # and incidental words such as "locked" in article titles.
    if sanity is not None and sanity.get("passed") is True and int(sanity.get("duplicate_paths") or 0) == 0:
        blocking_matches = []
    else:
        text_blocks = [
            json.dumps(report, ensure_ascii=False),
            json.dumps(sanity, ensure_ascii=False) if sanity is not None else "",
            read_text(sync_report_md),
            read_text(owner_report_path),
        ]
        blocking_matches = find_blocking_text(*text_blocks)
        if blocking_matches:
            reasons.extend(f"matched:{match}" for match in blocking_matches)

    if counts["error"]:
        reasons.append(f"errors={counts['error']}")

    if not aiw_safety.get("ok"):
        reasons.extend(f"aiw:{e}" for e in aiw_safety.get("errors") or [])

    if not non_aiw_health.get("ok"):
        reasons.extend(f"non_aiw:{e}" for e in non_aiw_health.get("errors") or [])

    status = "ok"
    if gate != "pass" or reasons:
        status = "blocked" if reasons else "error"

    changed_items = counts["create"] + counts["update"]
    topic = str(report.get("topic") or report.get("source") or "all")
    review_verdict = str(report.get("review_verdict") or "").strip()

    if review_verdict:
        latest_runs = (
            f"{out_dir.name} {topic}: article_count={report.get('article_count', changed_items)} "
            f"review={review_verdict}"
        )
    else:
        latest_runs = (
            f"{out_dir.name} {topic}: "
            f"create={counts['create']} update={counts['update']} skip={counts['skip']} "
            f"error={counts['error']}; aiw_map={aiw_safety.get('map_entries')} "
            f"aiw_unmapped={aiw_safety.get('aiw_unmapped')}"
        )

    manual_intervention = "none" if status == "ok" else "; ".join(dict.fromkeys(reasons))

    return {
        "status": status,
        "gate": gate,
        "date": out_dir.name,
        "create": counts["create"],
        "update": counts["update"],
        "skip": counts["skip"],
        "error": counts["error"],
        "changed_items": changed_items,
        "credential_env": "not_checked",
        "latest_runs": latest_runs,
        "owner_report": owner_report_for(out_dir, report),
        "sync_report": str(sync_report_md if sync_report_md.exists() else report_path),
        "manual_intervention": manual_intervention,
        "aiw_safety": aiw_safety,
        "non_aiw_health": non_aiw_health,
    }


def print_summary(summary, json_only=False):
    if json_only:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return

    print(f"status: {summary['status']}")
    print(f"gate: {summary['gate']}")
    print(f"create/update/skip: {summary['create']}/{summary['update']}/{summary['skip']}")
    print(f"changed_items: {summary['changed_items']}")
    aiw = summary.get("aiw_safety") or {}
    if aiw:
        print(
            f"aiw: map={aiw.get('map_entries')} unmapped={aiw.get('aiw_unmapped')} "
            f"upserts={aiw.get('aiw_upserts')} source_ok={aiw.get('source_path_ok')}"
        )
    non_aiw = summary.get("non_aiw_health") or {}
    if non_aiw:
        print(
            f"non_aiw: retired={non_aiw.get('retired_documents')} "
            f"suspicious={non_aiw.get('suspicious_counts')} "
            f"empty_sources={non_aiw.get('empty_active_sources')}"
        )
    print(f"credential_env: {summary['credential_env']}")
    print(f"latest_runs: {summary['latest_runs']}")
    print(f"owner_report: {summary['owner_report']}")
    print(f"sync_report: {summary['sync_report']}")
    print(f"manual_intervention: {summary['manual_intervention']}")


def main() -> int:
    args = parse_args()

    if args.date:
        out_dir = DAILY_DIR / args.date
    else:
        latest = latest_report_dir()
        if latest is None:
            summary = {
                "status": "error",
                "gate": "missing_report",
                "date": None,
                "create": 0,
                "update": 0,
                "skip": 0,
                "error": 1,
                "changed_items": 0,
                "credential_env": "not_checked",
                "latest_runs": "none",
                "owner_report": str(DAILY_DIR),
                "sync_report": str(DAILY_DIR),
                "manual_intervention": "no daily report directories found",
            }
            print_summary(summary, args.json)
            return 1 if args.strict else 0
        out_dir = latest

    try:
        summary = inspect_date(out_dir)
    except Exception as exc:
        summary = {
            "status": "error",
            "gate": "monitor_error",
            "date": out_dir.name,
            "create": 0,
            "update": 0,
            "skip": 0,
            "error": 1,
            "changed_items": 0,
            "credential_env": "not_checked",
            "latest_runs": f"{out_dir.name}: monitor error",
            "owner_report": str(out_dir),
            "sync_report": str(out_dir / "sync-report.json"),
            "manual_intervention": str(exc),
        }

    print_summary(summary, args.json)
    if args.strict and summary["status"] != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
