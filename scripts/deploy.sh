#!/usr/bin/env bash
set -euo pipefail

# Simple deployment script to update code, install deps, and restart the service.
# Usage (on the VM):
#   cd /home/<user>/Auto-Veille
#   ./scripts/deploy.sh

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${APP_DIR}/.venv"
SERVICE_NAME="autoveille"

echo "[DEPLOY] Working directory: ${APP_DIR}"
cd "${APP_DIR}"

if [ -d .git ]; then
  echo "[DEPLOY] Fetching latest code from origin/main..."
  git fetch --all
  git reset --hard origin/main
else
  echo "[DEPLOY] WARNING: No .git directory found. Skipping git update."
fi

echo "[DEPLOY] Ensuring virtualenv exists..."
if [ ! -d "${VENV}" ]; then
  python3 -m venv "${VENV}"
fi

echo "[DEPLOY] Installing/upgrading dependencies..."
source "${VENV}/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "[DEPLOY] Restarting service ${SERVICE_NAME}..."
if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart "${SERVICE_NAME}"
  sudo systemctl status "${SERVICE_NAME}" --no-pager --lines=20 || true
else
  echo "[DEPLOY] systemctl not available; skipping service restart."
fi

echo "[DEPLOY] Done."
