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
  .venv/bin/python - <<'PY'
import json
from datetime import datetime

from app.runtime_state import runtime_state_path


STALE_AFTER_SECONDS = 120
path = runtime_state_path('intake_worker')
print(f'intake_worker_state_path={path}')
if not path.exists():
    raise SystemExit('intake_worker_state=missing')

state = json.loads(path.read_text(encoding='utf-8'))
heartbeat = state.get('last_heartbeat_at')
if not heartbeat:
    raise SystemExit('intake_worker_heartbeat=missing')

heartbeat_at = datetime.fromisoformat(heartbeat)
now = datetime.now(tz=heartbeat_at.tzinfo)
age_seconds = int((now - heartbeat_at).total_seconds())
print(f'intake_worker_heartbeat_age_seconds={age_seconds}')
if age_seconds > STALE_AFTER_SECONDS:
    raise SystemExit('intake_worker_heartbeat=stale')
PY
  .venv/bin/python - <<'PY'
import asyncio

from sqlalchemy import text

from app.database import SessionLocal


PROCESSING_STALE_MINUTES = 10


async def main() -> None:
    async with SessionLocal() as session:
        stale_result = await session.execute(
            text(
                '''
                SELECT count(*) AS count
                FROM intake_queue
                WHERE status = 'processing'
                  AND locked_at IS NOT NULL
                  AND locked_at < now() - (:stale_minutes || ' minutes')::interval
                '''
            ),
            {'stale_minutes': str(PROCESSING_STALE_MINUTES)},
        )
        stale_processing_count = int(stale_result.scalar_one())

        exhausted_result = await session.execute(
            text(
                '''
                SELECT count(*) AS count
                FROM intake_queue
                WHERE status = 'failed'
                  AND attempts >= max_attempts
                '''
            )
        )
        exhausted_failed_count = int(exhausted_result.scalar_one())

    print(f'intake_queue_stale_processing_count={stale_processing_count}')
    print(f'intake_queue_exhausted_failed_count={exhausted_failed_count}')
    if stale_processing_count:
        raise SystemExit('intake_queue_processing=stale')
    if exhausted_failed_count:
        raise SystemExit('intake_queue_failed=exhausted')


asyncio.run(main())
PY
"
