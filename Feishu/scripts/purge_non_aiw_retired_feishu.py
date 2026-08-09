#!/usr/bin/env /opt/homebrew/bin/python3.14
# -*- coding: utf-8 -*-
"""Purge non-AIW retired/stale Feishu documents and local sync state.

Deletes only document rows explicitly listed in config/sources.json retired_items,
excluding aiw/*. Uses sqlite tokens for exact remote Drive deletion; then removes
matching publish-state document/node keys and sqlite rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from feishu_sync.feishu_api import FeishuApiError, feishu_delete  # noqa: E402
from feishu_sync.feishu_auth import fetch_tenant_access_token  # noqa: E402


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def delete_docx(token: str, obj_token: str) -> None:
    feishu_delete(f"/drive/v1/files/{obj_token}?type=docx", token, body=None)


def load_targets(config_path: Path, include_sources: set[str] | None) -> list[str]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    items = []
    for key in cfg.get("retired_items") or []:
        key = str(key)
        if key.startswith("aiw/"):
            continue
        if "/" not in key:
            continue
        sid, _ = key.split("/", 1)
        if include_sources and sid not in include_sources:
            continue
        items.append(key)
    return sorted(set(items))


def load_db_rows(db_path: Path, keys: list[str]) -> dict[str, dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = {}
    try:
        for key in keys:
            sid, item = key.split("/", 1)
            row = conn.execute(
                "select source_id, source_item_id, title, feishu_doc_id, wiki_node_token from content_items where source_id=? and source_item_id=?",
                (sid, item),
            ).fetchone()
            if row:
                rows[key] = dict(row)
    finally:
        conn.close()
    return rows


def purge_local_state(*, state_path: Path, db_path: Path, keys: list[str], rows: dict[str, dict], dry_run: bool) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    docs = state.get("documents") or {}
    nodes = state.get("nodes") or {}
    node_tokens = {str(r.get("wiki_node_token") or "") for r in rows.values() if r.get("wiki_node_token")}

    doc_removed = [k for k in keys if k in docs]
    node_removed = []
    for k, v in list(nodes.items()):
        if isinstance(v, dict) and str(v.get("node_token") or "") in node_tokens:
            node_removed.append(k)

    if not dry_run:
        bak = state_path.with_suffix(state_path.suffix + f".bak-non-aiw-purge-{time.strftime('%Y%m%d%H%M%S')}")
        bak.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for k in doc_removed:
            docs.pop(k, None)
        for k in node_removed:
            nodes.pop(k, None)
        state["documents"] = docs
        state["nodes"] = nodes
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        conn = sqlite3.connect(str(db_path))
        try:
            for key in keys:
                sid, item = key.split("/", 1)
                conn.execute("delete from sync_events where source_id=? and source_item_id=?", (sid, item))
                conn.execute("delete from content_items where source_id=? and source_item_id=?", (sid, item))
            conn.commit()
        finally:
            conn.close()
    return {"documents_removed": len(doc_removed), "nodes_removed": len(node_removed), "db_rows_removed": len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge non-AIW retired Feishu docs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-remote", action="store_true")
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "sources.json")
    ap.add_argument("--publish-state", type=Path, default=ROOT / "registry" / "publish-state.json")
    ap.add_argument("--registry", type=Path, default=ROOT / "registry" / "feishu-sync.sqlite")
    ap.add_argument("--source", action="append", help="Limit to source id; repeatable")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    include = set(args.source or []) or None
    keys = load_targets(args.config, include)
    if args.limit is not None:
        keys = keys[: args.limit]
    rows = load_db_rows(args.registry, keys)

    summary = {
        "dry_run": args.dry_run,
        "target_keys": len(keys),
        "db_rows_found": len(rows),
        "missing_db_rows": len(keys) - len(rows),
        "by_source": {},
        "remote_deleted": 0,
        "remote_errors": 0,
        "remote_skipped_no_doc_token": 0,
        "samples": keys[:10],
    }
    for k in keys:
        sid = k.split("/", 1)[0]
        summary["by_source"][sid] = summary["by_source"].get(sid, 0) + 1

    if not args.skip_remote:
        app_id = _env("FEISHU_APP_ID")
        app_secret = _env("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            print("missing FEISHU_APP_ID/FEISHU_APP_SECRET", file=sys.stderr)
            return 2
        token = fetch_tenant_access_token(app_id, app_secret).token
        for key, row in rows.items():
            doc = str(row.get("feishu_doc_id") or "").strip()
            if not doc:
                summary["remote_skipped_no_doc_token"] += 1
                continue
            if args.dry_run:
                summary["remote_deleted"] += 1
                continue
            try:
                delete_docx(token, doc)
                summary["remote_deleted"] += 1
                print(f"[deleted] {key} {row.get('title','')}")
                time.sleep(0.12)
            except FeishuApiError as exc:
                summary["remote_errors"] += 1
                print(f"[error] {key}: {exc}", file=sys.stderr)
                time.sleep(0.35)

    local = purge_local_state(state_path=args.publish_state, db_path=args.registry, keys=keys, rows=rows, dry_run=args.dry_run)
    summary["local"] = local
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 3 if summary["remote_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
