#!/usr/bin/env bash
# FAST training for the 2-hour crunch. ACT trains from scratch but cheaply —
# usable single-task pour policy in ~30-45 min on an A100, leaving time to deploy.
set -euo pipefail

# --- one-time setup on the GPU box ---
#   python -m venv .venv && source .venv/bin/activate
#   pip install "lerobot[feetech]"      # ACT needs no extra deps
#   hf auth login                        # token with READ access to duico/cuda_libre_pour
# -------------------------------------

DATASET="${DATASET:-duico/cuda_libre_pour}"
STEPS="${STEPS:-30000}"      # ACT steps are fast; 30k ~ 30-45 min on A100
BATCH="${BATCH:-8}"          # ACT's usual batch size

lerobot-train \
  --policy.type=act \
  --dataset.repo_id="$DATASET" \
  --batch_size="$BATCH" \
  --steps="$STEPS" \
  --output_dir=outputs/train/cuda_libre_act \
  --job_name=cuda_libre_act \
  --policy.device=cuda \
  --wandb.enable=false \
  --policy.push_to_hub=false \
  --save_freq=5000           # checkpoints every 5k so you can deploy early if time runs short

# Checkpoints: outputs/train/cuda_libre_act/checkpoints/<step>/pretrained_model
