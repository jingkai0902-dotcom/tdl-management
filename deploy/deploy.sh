#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bots/tdl/backend"
BACKEND_SERVICE_PATH="/etc/systemd/system/tdl-backend.service"
STREAM_SERVICE_PATH="/etc/systemd/system/tdl-stream-bot.service"
NGINX_SITE="${NGINX_SITE:-}"
SERVICE_USER="${SERVICE_USER:-tdl}"

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

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir /opt/bots/tdl --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
chmod 0640 "$APP_DIR/.env"

sed "s/^User=.*/User=$SERVICE_USER/" deploy/tdl-backend.service > "$BACKEND_SERVICE_PATH"
sed "s/^User=.*/User=$SERVICE_USER/" deploy/tdl-stream-bot.service > "$STREAM_SERVICE_PATH"
chmod 0644 "$BACKEND_SERVICE_PATH" "$STREAM_SERVICE_PATH"
systemctl daemon-reload
systemctl enable tdl-backend.service
systemctl enable tdl-stream-bot.service
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