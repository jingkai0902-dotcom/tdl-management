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

systemctl is-active --quiet tdl-backend.service
systemctl is-active --quiet tdl-stream-bot.service
systemctl is-active --quiet tdl-intake-worker.service
systemctl is-active --quiet tdl-pilot-metrics.timer
echo
echo "TDL smoke test passed"
