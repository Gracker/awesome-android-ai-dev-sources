#!/usr/bin/env bash
set -euo pipefail

DATE=""
DRY_RUN=0
TOPIC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      DATE="${2:-}"
      shift 2
      ;;
    --topic)
      TOPIC="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$DATE" ]]; then
  echo "--date is required" >&2
  exit 2
fi

if [[ "$DRY_RUN" != "1" ]]; then
  echo "This local cron entrypoint only supports --dry-run; no Feishu writes were made." >&2
  exit 2
fi

ROOT="/Users/gracker/.openclaw/workspace/Feishu"
ANDROID_MEMORY_ROOT="/Users/gracker/Library/Mobile Documents/iCloud~md~obsidian/Documents/Writer/android-memory"
RENDERING_ROOT="/Users/gracker/Library/Mobile Documents/iCloud~md~obsidian/Documents/Writer/rendering_pipelines"

if [[ -z "$TOPIC" ]]; then
  TOPIC="rendering-pipelines"
  ANDROID_REVIEW="$ANDROID_MEMORY_ROOT/openclaw/reviews/$DATE-daily-review.md"
  RENDERING_REVIEW="$RENDERING_ROOT/openclaw/reviews/$DATE-daily-review.md"
  if [[ -f "$ANDROID_REVIEW" && ( ! -f "$RENDERING_REVIEW" || "$ANDROID_REVIEW" -nt "$RENDERING_REVIEW" ) ]]; then
    TOPIC="android-memory"
  fi
fi

case "$TOPIC" in
  android-memory)
    TOPIC_ROOT="$ANDROID_MEMORY_ROOT"
    ARTICLE_PATTERN="P*.md"
    ;;
  rendering-pipelines)
    TOPIC_ROOT="$RENDERING_ROOT"
    ARTICLE_PATTERN="S*.md"
    ;;
  *)
    echo "unknown topic: $TOPIC" >&2
    exit 2
    ;;
esac
OUT_DIR="$ROOT/generated/daily/$DATE"
mkdir -p "$OUT_DIR"

REVIEW="$TOPIC_ROOT/openclaw/reviews/$DATE-daily-review.md"
ARTICLE_COUNT="$(find "$TOPIC_ROOT" -maxdepth 1 -type f -name "$ARTICLE_PATTERN" | wc -l | tr -d ' ')"
VERDICT="missing-review"
if [[ -f "$REVIEW" ]]; then
  VERDICT="$(grep -m 1 '^- verdict:' "$REVIEW" | sed -E 's/.*`([^`]+)`.*/\1/')"
fi

cat > "$OUT_DIR/sync-report.md" <<REPORT
# Feishu Daily Sync Dry Run - $DATE

- dry_run: true
- remote_writes: 0
- topic: $TOPIC
- article_count: $ARTICLE_COUNT
- review_report: $REVIEW
- review_verdict: $VERDICT

No Feishu API write was attempted.
REPORT

cat > "$OUT_DIR/sync-report.json" <<REPORT
{
  "date": "$DATE",
  "dry_run": true,
  "remote_writes": 0,
  "topic": "$TOPIC",
  "article_count": $ARTICLE_COUNT,
  "review_report": "$REVIEW",
  "review_verdict": "$VERDICT"
}
REPORT

echo "dry-run pass (remote_writes=0, topic=$TOPIC, articles=$ARTICLE_COUNT, review=$VERDICT)"
echo "$OUT_DIR/sync-report.md"
