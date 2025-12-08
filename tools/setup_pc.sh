#!/usr/bin/env bash
set -euo pipefail

# Simple PC bootstrap for ~/archimedes
# Usage:
#   cd /home/archimedes/ドキュメント
#   bash tools/setup_pc.sh
# This script will:
# - create ~/archimedes/venv (virtualenv)
# - install packages from requirements.txt
# - print quick start commands to run joystick server

DEST_DIR="$HOME/archimedes"
VENV_DIR="$DEST_DIR/venv"

echo "Using DEST_DIR=$DEST_DIR"

if [ ! -d "$DEST_DIR" ]; then
  echo "Creating $DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

PY3=$(command -v python3 || true)
if [ -z "$PY3" ]; then
  echo "python3 not found in PATH. Please install Python 3." >&2
  exit 1
fi

echo "Creating virtualenv at $VENV_DIR (python: $PY3)"
$PY3 -m venv "$VENV_DIR"

echo "Activating virtualenv and upgrading pip..."
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel

REQ_FILE="requirements.txt"
if [ ! -f "$REQ_FILE" ]; then
  echo "Warning: $REQ_FILE not found in current directory. Creating minimal requirements." 
  cat > "$REQ_FILE" <<'REQ'
pygame>=2.0.0
requests>=2.25.1
REQ
fi

echo "Installing requirements from $REQ_FILE"
pip install -r "$REQ_FILE"

echo "Setup complete. Quick start (from repo root):"
echo "  # activate venv"
echo "  source $VENV_DIR/bin/activate"
echo "  # run joystick HTTP server (allow remote Pi to poll):"
echo "  PYTHONPATH=. python3 tools/joy_server.py --host 0.0.0.0 --port 8000"
echo "  # or run UDP client to push to Pi (replace <PI_IP>):"
echo "  PYTHONPATH=. python3 tools/joy_net_client.py --host <PI_IP> --port 5005"

echo "If you want systemd templates, see tools/systemd/*.service"

deactivate 2>/dev/null || true

exit 0
