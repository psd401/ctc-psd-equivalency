#!/bin/bash
# Re-scrape the three Acalog colleges at the crawl rate their robots.txt asks
# for (crawl-delay: 120). At that rate a full pass is roughly:
#
#   olympic     ~1246 courses  ~41h
#   greenriver  ~1378 courses  ~46h
#   pierce       ~947 courses  ~32h
#
# so this is an overnight-and-then-some job, one college at a time. Run it
# detached and check the log; it survives terminal exit:
#
#   nohup ./run_acalog_overnight.sh > /dev/null 2>&1 &
#   tail -f logs/acalog-<date>.log
#
# Safe to interrupt. Each college writes only after its own scrape finishes,
# and build_dataset refuses to overwrite a catalog file when the new scrape
# returns under COLLAPSE_THRESHOLD of what is already on disk — so a WAF
# challenge partway through leaves the existing data intact.
#
# Override the rate with ACALOG_DELAY (seconds) if the colleges tell us a
# different figure is fine. Do not lower it on a hunch: crawling 240x faster
# than the published policy is what got content.php challenged in the first
# place.
set -uo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-$(pwd)/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"

mkdir -p logs
LOG="logs/acalog-$(date +%Y-%m-%d-%H%M).log"
: "${ACALOG_DELAY:=120}"
export ACALOG_DELAY

{
  echo "=== Acalog re-scrape started $(date) — delay ${ACALOG_DELAY}s per request"
  echo

  # A smoke test on 2026-09-02 showed content.php answering with the WAF
  # challenge even at 45s and 90s waits, so this is a standing rule rather than
  # a rate trip that clears in minutes. It may still decay after a long quiet
  # period, so retry each college on a wide interval overnight instead of
  # giving up in two minutes. If every attempt is refused, that is the answer:
  # the crawl needs the colleges' cooperation, not a slower loop.
  RETRIES="${ACALOG_RETRIES:-8}"
  RETRY_GAP="${ACALOG_RETRY_GAP:-3600}"

  for inst in olympic greenriver pierce; do
    ok=0
    for attempt in $(seq 1 "$RETRIES"); do
      echo "--- $inst: attempt $attempt/$RETRIES starting $(date)"
      if "$PYTHON" build_dataset.py "$inst"; then
        echo "--- $inst: OK $(date)"
        ok=1
        break
      fi
      echo "--- $inst: attempt $attempt refused $(date) — existing catalog untouched"
      if [ "$attempt" -lt "$RETRIES" ]; then
        echo "    sleeping ${RETRY_GAP}s before retry"
        sleep "$RETRY_GAP"
      fi
    done
    [ "$ok" -eq 1 ] || echo "!!! $inst: all $RETRIES attempts refused — needs college cooperation"
    echo
  done

  echo "=== finished $(date)"
  echo
  echo "Next steps if the colleges came back clean:"
  echo "  1. Read each 'acalog: <inst>: N/M pages parsed' line above."
  echo "     A zero or a large gap means a blocked crawl, NOT an empty catalog."
  echo "  2. Diff against the previous scrape before publishing."
  echo "  3. $PYTHON merge_catalogs.py && $PYTHON classify_courses.py && $PYTHON build_html.py"
} 2>&1 | tee "$LOG"
