#!/usr/bin/env bash
# Run on the CLOUD GPU box (Linux + NVIDIA CUDA). Fine-tunes SmolVLA on the
# cuda_libre_pour dataset, starting from the pretrained lerobot/smolvla_base.
set -euo pipefail

# --- one-time setup on the GPU box ---
#   python -m venv .venv && source .venv/bin/activate
#   pip install "lerobot[smolvla]"
#   hf auth login            # paste an HF token with READ access to duico/cuda_libre_pour
# -------------------------------------

DATASET="${DATASET:-duico/cuda_libre_pour}"
STEPS="${STEPS:-12000}"      # tuned for H100 + ~40 min; raise later for better quality
BATCH="${BATCH:-64}"         # H100 80GB handles this easily; drop to 32/16 on smaller cards

lerobot-train \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id="$DATASET" \
  --batch_size="$BATCH" \
  --steps="$STEPS" \
  --save_freq=2000 \
  --output_dir=outputs/train/cuda_libre_smolvla \
  --job_name=cuda_libre_smolvla \
  --policy.device=cuda \
  --wandb.enable=false \
  --policy.push_to_hub=false

# Result: outputs/train/cuda_libre_smolvla/checkpoints/last/pretrained_model
# (verify exact flags on the box with: lerobot-train --help)
