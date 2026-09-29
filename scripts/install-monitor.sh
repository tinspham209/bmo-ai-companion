#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_DIR="$ROOT_DIR/services/bmo-monitor"
VENV_DIR="$SERVICE_DIR/.venv"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SERVICE_DIR/requirements.txt"

echo "Installed bmo-monitor dependencies in $VENV_DIR"
echo "To run locally:"
echo "  cd $SERVICE_DIR && .venv/bin/python main.py"
