#!/usr/bin/env bash
set -euo pipefail

for attempt in {1..10}; do
  if curl -fsS http://127.0.0.1:8010/health; then
    break
  fi
  if [[ "$attempt" == "10" ]]; then
    exit 1
  fi
  sleep 1
done

entry_html="$(curl -fsS http://127.0.0.1:8010/)"
grep -q 'TDL管理助手' <<<"$entry_html"
grep -q '复制名称' <<<"$entry_html"
grep -q './health' <<<"$entry_html"

systemctl is-active --quiet tdl-backend.service
systemctl is-active --quiet tdl-stream-bot.service
systemctl is-active --quiet tdl-intake-worker.service
systemctl is-active --quiet tdl-pilot-metrics.timer
echo
echo "TDL smoke test passed"
