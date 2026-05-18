#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-root@182.92.9.69}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
APP_DIR="${APP_DIR:-/opt/bots/tdl/backend}"

git ls-files -z | rsync -az \
  -e "ssh -o StrictHostKeyChecking=no -i $SSH_KEY" \
  --from0 \
  --files-from=- \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  ./ "$REMOTE_HOST:$APP_DIR/"

ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$REMOTE_HOST" "
  set -euo pipefail
  cd '$APP_DIR'
  PYTHON_BIN=python3.11 bash deploy/deploy.sh
  bash deploy/smoke-test.sh
"
