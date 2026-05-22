#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-root@182.92.9.69}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
APP_DIR="${APP_DIR:-/opt/bots/tdl/backend}"

ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$REMOTE_HOST" "
  set -euo pipefail
  cd '$APP_DIR'
  printf 'app_dir=%s\n' '$APP_DIR'
  printf 'backend='
  systemctl is-active tdl-backend.service
  printf 'stream='
  systemctl is-active tdl-stream-bot.service
  printf 'intake_worker='
  systemctl is-active tdl-intake-worker.service
  printf 'pilot_metrics_timer='
  systemctl is-active tdl-pilot-metrics.timer
  printf 'pilot_metrics_next='
  systemctl show tdl-pilot-metrics.timer --property=NextElapseUSecRealtime --value
  printf 'health='
  curl -fsS http://127.0.0.1:8010/health
  printf '\n'
  .venv/bin/python - <<'PY'
from app.config import get_settings

settings = get_settings()
print(f'template_set={bool(settings.dingtalk_tdl_card_template_id)}')
print(
    'require_interactive='
    f'{settings.dingtalk_require_interactive_reminder_cards}'
)
PY
"
