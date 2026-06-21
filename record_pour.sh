#!/usr/bin/env bash
# Record SO-101 pour episodes for the cuda-libre demo.
# Fill in the 4 vars below (get them from the steps in the chat), then: bash record_pour.sh
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

# --- FILL THESE IN ---
FOLLOWER_PORT="/dev/cu.usbmodem5B140320991"   # robot arm (the one that pours) — from identify_arms.py
LEADER_PORT="/dev/cu.usbmodem5B140296591"     # the arm you move by hand        — from identify_arms.py
CAM_INDEX=0                             # 0 = arm-mounted cam (usable). 1 = MacBook webcam (your face). only 0-1 exist.
HF_USER="duico"                        # for push_to_hub (run: huggingface-cli login)
# ---------------------

NUM_EPISODES="${1:-50}"                 # override: bash record_pour.sh 60
FRESH="${FRESH:-false}"                 # FRESH=true starts a new dataset (existing one is BACKED UP first, never deleted)
export GRIP_TARGET="${GRIP_TARGET:-23.155}" # gripper width (0-100) that holds the glass; shows as target line in rerun

# DATA-SAFE policy: never delete captures. Default = resume/append into the existing dataset.
# FRESH=true backs up the existing dataset (MOVE, not delete) before starting clean.
DATASET_DIR="$HOME/.cache/huggingface/lerobot/$HF_USER/cuda_libre_pour"
if [ "$FRESH" = "true" ] && [ -d "$DATASET_DIR" ]; then
  BACKUP_DIR="${DATASET_DIR}.bak-$(date +%Y%m%d-%H%M%S)"
  echo "[record_pour] FRESH=true → backing up existing dataset to: $BACKUP_DIR"
  mv "$DATASET_DIR" "$BACKUP_DIR"
fi
# Resume automatically if a dataset already exists (append); otherwise first run.
if [ -d "$DATASET_DIR" ]; then RESUME=true; else RESUME=false; fi
echo "[record_pour] resume=$RESUME  (dataset: $DATASET_DIR)"

python record_pour.py \
  --robot.type=so101_follower \
  --robot.id=my_follower \
  --robot.port="$FOLLOWER_PORT" \
  --robot.cameras="{ front: {type: opencv, index_or_path: $CAM_INDEX, width: 640, height: 480, fps: 15, warmup_s: 5}}" \
  --teleop.type=so101_leader \
  --teleop.id=my_leader \
  --teleop.port="$LEADER_PORT" \
  --dataset.repo_id="$HF_USER/cuda_libre_pour" \
  --dataset.single_task="pour the shot into the cup" \
  --dataset.fps=15 \
  --dataset.num_episodes="$NUM_EPISODES" \
  --dataset.episode_time_s=120 \
  --dataset.reset_time_s=3600 \
  --resume="$RESUME" \
  --display_data=true \
  --dataset.streaming_encoding=true \
  --dataset.encoder_threads=2 \
  --dataset.push_to_hub=true
