#!/usr/bin/env bash
# Run the trained SmolVLA pour policy on the SO-101 (on the Mac, with the arm).
# Step 1 pulls the latest checkpoint from the GPU box; step 2 rolls out the policy.
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

# --- box + arm config ---
BOX="root@205.196.17.50"; PORT=8861; KEY=~/.ssh/id_postscarcity
FOLLOWER_PORT="/dev/cu.usbmodem5B140320991"
CAM_INDEX=0
CKPT_STEP="${CKPT_STEP:-last}"   # or a specific step like 6000
# ------------------------

# 1) pull the checkpoint (the trained policy weights) from the box — skip if already local
mkdir -p policy_cuda_libre
if [ ! -f policy_cuda_libre/model.safetensors ]; then
  scp -P "$PORT" -i "$KEY" -r \
    "$BOX:/root/outputs/train/cuda_libre_smolvla_v2/checkpoints/$CKPT_STEP/pretrained_model/." \
    ./policy_cuda_libre/
else
  echo "[deploy] checkpoint already present, skipping download"
fi

# Eval rollouts are re-recorded each run; if the dir exists, back it up (never delete) so the run can start.
EVAL_DIR="$HOME/.cache/huggingface/lerobot/duico/eval_cuda_libre"
if [ -d "$EVAL_DIR" ]; then
  mv "$EVAL_DIR" "${EVAL_DIR}.bak-$(date +%Y%m%d-%H%M%S)"
  echo "[deploy] backed up existing eval dir"
fi

# 2) roll out the policy on the arm (NO teleop — the policy drives it).
#    rename_map MUST match training (dataset 'front' -> policy 'camera1').
python deploy_infer.py \
  --robot.type=so101_follower \
  --robot.id=my_follower \
  --robot.port="$FOLLOWER_PORT" \
  --robot.cameras="{ camera1: {type: opencv, index_or_path: $CAM_INDEX, width: 640, height: 480, fps: 15, warmup_s: 5}}" \
  --policy.path=./policy_cuda_libre \
  --policy.device=mps \
  --dataset.repo_id=duico/eval_cuda_libre \
  --dataset.single_task="pour the right shot glass into the large plastic cup, then pour the left shot glass into the large plastic cup" \
  --dataset.num_episodes=5 \
  --dataset.fps=15 \
  --dataset.episode_time_s=60 \
  --display_data=true \
  --dataset.push_to_hub=false
