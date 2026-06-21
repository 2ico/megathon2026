#!/usr/bin/env bash
# Start the preloaded cocktail server. Keep this running; it loads the model ONCE,
# then POST /make_cocktail fires a pour instantly. (Only the follower arm is needed.)
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

export FOLLOWER_PORT="/dev/cu.usbmodem5B140320991"
export CAM_INDEX=0
export CKPT=./policy_cuda_libre
export DEVICE=mps
export FPS=15
export POUR_SECONDS=55      # how long one pour runs (policy gives no "done" signal)
export PORT=8088

python cocktail_server.py
