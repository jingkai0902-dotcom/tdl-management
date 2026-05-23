#!/usr/bin/env bash
set -euo pipefail

SMOKE_RETRY_ATTEMPTS="${SMOKE_RETRY_ATTEMPTS:-30}"
SMOKE_RETRY_DELAY_SECONDS="${SMOKE_RETRY_DELAY_SECONDS:-1}"

curl_with_retry() {
  local url="$1"
  local attempt
  for ((attempt = 1; attempt <= SMOKE_RETRY_ATTEMPTS; attempt += 1)); do
    if curl -fsS "$url"; then
      return 0
    fi
    if [[ "$attempt" == "$SMOKE_RETRY_ATTEMPTS" ]]; then
      return 1
    fi
    sleep "$SMOKE_RETRY_DELAY_SECONDS"
  done
}

curl_with_retry http://127.0.0.1:8010/health

entry_html="$(curl_with_retry http://127.0.0.1:8010/)"
grep -q 'TDL管理助手' <<<"$entry_html"
grep -q '复制名称' <<<"$entry_html"
grep -q './health' <<<"$entry_html"

systemctl is-active --quiet tdl-backend.service
systemctl is-active --quiet tdl-stream-bot.service
systemctl is-active --quiet tdl-intake-worker.service
systemctl is-active --quiet tdl-pilot-metrics.timer
echo
echo "TDL smoke test passed"
