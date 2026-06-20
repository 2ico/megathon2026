#!/usr/bin/env bash
# SO-101 teleop — macOS install script.
# Creates a Python 3.11 venv (.venv in the repo root) and installs lerobot[feetech].
#
# Usage:
#   bash teleop/install_mac.sh
set -euo pipefail

# Repo root = parent of this script's dir.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$ROOT/.venv"

echo "==> Repo root: $ROOT"

# Prefer uv (fast, can fetch Python 3.11); fall back to system python3.
if command -v uv >/dev/null 2>&1; then
  echo "==> Creating venv with uv (Python 3.11)..."
  uv venv --python 3.11 "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  echo "==> Installing lerobot[feetech]..."
  uv pip install "lerobot[feetech]"
else
  echo "==> uv not found. Install it with:  brew install uv   (recommended)"
  echo "==> Falling back to python3 venv (needs Python 3.10-3.12; 3.14 has no torch wheels)."
  PY="$(command -v python3.11 || command -v python3)"
  echo "==> Using $PY"
  "$PY" -m venv "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  python -m pip install --upgrade pip
  echo "==> Installing lerobot[feetech]..."
  pip install "lerobot[feetech]"
fi

echo
echo "==> Done. Verify:"
python -c "import lerobot; print('lerobot', lerobot.__version__)"
echo
echo "Next (this machine can be EITHER role):"
echo "  source $VENV/bin/activate"
echo "  lerobot-find-port          # find your arm's serial port"
echo "  # LEADER  machine -> run leader_client.py"
echo "  # FOLLOWER machine -> run follower_server.py"
echo "  # see teleop/README.md"
