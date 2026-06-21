#!/usr/bin/env bash
# HG-DAgger: policy drives the SO-101; press 'i' to take over with the leader and
# record corrections. BOTH arms (leader + follower) must be plugged into this Mac.
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

FOLLOWER_PORT="/dev/cu.usbmodem5B140320991"
LEADER_PORT="/dev/cu.usbmodem5B140296591"
CAM_INDEX=0

# back up an existing dagger dataset (never delete) so the run can start fresh
DD="$HOME/.cache/huggingface/lerobot/duico/cuda_libre_dagger"
if [ -d "$DD" ]; then mv "$DD" "${DD}.bak-$(date +%Y%m%d-%H%M%S)"; echo "[hg] backed up existing dagger dataset"; fi

python hg_dagger.py \
  --follower-port "$FOLLOWER_PORT" \
  --leader-port "$LEADER_PORT" \
  --cam-index "$CAM_INDEX" \
  --checkpoint ./policy_cuda_libre \
  --repo-id duico/cuda_libre_dagger \
  --device mps \
  --fps 15 \
  --episodes 20
