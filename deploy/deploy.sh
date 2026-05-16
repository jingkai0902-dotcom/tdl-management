#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bots/tdl/backend"
BACKEND_SERVICE_PATH="/etc/systemd/system/tdl-backend.service"
STREAM_SERVICE_PATH="/etc/systemd/system/tdl-stream-bot.service"
NGINX_SITE="${NGINX_SITE:-}"

python3 - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("python3.11+ is required")
PY

cd "$APP_DIR"

if [[ ! -f ".env" ]]; then
  echo "missing $APP_DIR/.env"
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head

install -m 0644 deploy/tdl-backend.service "$BACKEND_SERVICE_PATH"
install -m 0644 deploy/tdl-stream-bot.service "$STREAM_SERVICE_PATH"
systemctl daemon-reload
systemctl enable --now tdl-backend.service
systemctl enable --now tdl-stream-bot.service
systemctl restart tdl-backend.service
systemctl restart tdl-stream-bot.service

if [[ -n "$NGINX_SITE" ]]; then
  if ! grep -q 'location /tdl/' "$NGINX_SITE"; then
    echo "merge deploy/nginx-tdl.conf into $NGINX_SITE before reloading nginx"
  else
    nginx -t
    systemctl reload nginx
  fi
else
  echo "NGINX_SITE not set; skipped nginx reload"
fi

systemctl status tdl-backend.service --no-pager
systemctl status tdl-stream-bot.service --no-pager