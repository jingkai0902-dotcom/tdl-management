#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:8010/health
systemctl is-active --quiet tdl-backend.service
systemctl is-active --quiet tdl-stream-bot.service
echo
echo "TDL smoke test passed"