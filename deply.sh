#!/usr/bin/env bash
set -Eeuo pipefail

# Move to repo root (script's directory)
cd "$(dirname "$0")"

usage() {
  echo "Usage: $0 [update|install|restart|start|stop]"
  echo " - update  : git pull, install deps, DB setup, (optional) restart"
  echo " - install : create venv and install requirements"
  echo " - restart : restart systemd service (if configured)"
  echo " - start   : start app with gunicorn (fallback if no systemd)"
  echo " - stop    : stop gunicorn fallback"
}

ensure_venv() {
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -U pip wheel
  if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt
  fi
}

load_env() {
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
  fi
}

migrate_db() {
  if [[ -f setup_db.py ]]; then
    python3 setup_db.py || true
  fi
}

pdf_deps_check() {
  if [[ "$(uname -s | tr '[:upper:]' '[:lower:]')" == "linux" ]]; then
    if ! command -v wkhtmltopdf >/dev/null 2>&1; then
      echo "ℹ️ wkhtmltopdf not found. If using PDF_ENGINE=wkhtmltopdf, install it:"
      echo "   sudo apt-get update && sudo apt-get install -y wkhtmltopdf"
    fi
  fi
}

restart_service() {
  # Prefer systemd if a unit exists; otherwise fallback to gunicorn
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files | grep -q '^auto-veille.service'; then
      sudo systemctl restart auto-veille.service || true
      sudo systemctl status auto-veille.service --no-pager || true
      return 0
    fi
  fi
  echo "ℹ️ No systemd unit 'auto-veille.service' found. Starting fallback with gunicorn..."
  stop_fallback || true
  start_fallback
}

start_fallback() {
  # shellcheck disable=SC1091
  source .venv/bin/activate
  export FLASK_ENV=${FLASK_ENV:-production}
  PKG_BIND=${BIND_ADDR:-"127.0.0.1:8000"}
  if command -v gunicorn >/dev/null 2>&1; then
    nohup gunicorn -b "$PKG_BIND" app:app >/tmp/auto-veille.out 2>&1 &
    echo $! > /tmp/auto-veille.pid
    echo "Started gunicorn on $PKG_BIND (PID $(cat /tmp/auto-veille.pid))"
  else
    nohup python3 app.py >/tmp/auto-veille.out 2>&1 &
    echo $! > /tmp/auto-veille.pid
    echo "Started python app.py (PID $(cat /tmp/auto-veille.pid))"
  fi
}

stop_fallback() {
  if [[ -f /tmp/auto-veille.pid ]]; then
    kill "$(cat /tmp/auto-veille.pid)" || true
    rm -f /tmp/auto-veille.pid
    echo "Stopped fallback process"
  fi
}

update() {
  echo "🔄 Updating repository..."
  git fetch --all
  git pull --ff-only
  echo "📦 Ensuring virtualenv and dependencies..."
  ensure_venv
  load_env
  pdf_deps_check
  echo "🗃️  Running DB setup (if any)..."
  migrate_db
  echo "🚀 Restarting service or starting fallback..."
  restart_service
  echo "✅ Update complete."
}

cmd="${1:-update}"
case "$cmd" in
  update) update ;;
  install) ensure_venv ;;
  restart) restart_service ;;
  start) ensure_venv; load_env; start_fallback ;;
  stop) stop_fallback ;;
  *) usage; exit 1 ;;
esac
