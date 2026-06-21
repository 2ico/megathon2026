# CUDA Libre 🤖🍹

Teaching a [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101) arm to mix a
**Cuda Libre** — pour two shots (rum + cola; water during training) into a cup —
autonomously, via imitation learning with **SmolVLA**.

## The task

A single end-to-end two-pour sequence the policy runs from one wrist camera + a
language instruction:

> *"pour the right shot glass into the large plastic cup, then pour the left shot glass into the large plastic cup"*

Scene: **2 shot glasses + 1 cup**. The policy does the whole sequence — locate, grasp,
pour, return, repeat — with no scripting or teleop.

## How we trained it

The pipeline, end to end (scripts in this repo):

### 1. Teleoperated data collection — `record_pour.sh` / `record_pour.py`
- SO-101 leader→follower teleoperation, recorded with `lerobot-record`.
- One wrist-mounted camera (640×480 @ 15 fps). `record_pour.py` wraps the recorder to
  overlay a **gripper-width target line** in the rerun viewer, so grasps stay consistent
  across demos.
- Recorded on **water** — a clean stand-in for rum/cola (near-identical pour dynamics, no
  sticky mess, and it transfers directly to the real liquids).
- **60 episodes** (~37k frames), each a full two-pour demo, with the glasses at varied
  positions. Saved as a `LeRobotDataset` and pushed to the HF Hub.

### 2. Policy fine-tuning — `train_smolvla.sh`
- Fine-tuned **SmolVLA** from `lerobot/smolvla_base` on a cloud **H100** (RunPod).
- 18,000 steps, batch size 64, ~1.5 h, logged to Weights & Biases.
- The single camera is mapped to the policy's expected `camera1` input.
- (`train_act.sh` is an ACT alternative for faster, lighter training.)

### 3. Deployment — `deploy_pour.sh` / `deploy_infer.py`
- Runs the trained policy on a Mac (Apple **MPS**), driving the arm directly (no teleop).
- `cocktail_server.py` keeps the model **preloaded** and exposes `POST /make_cocktail`
  (and `POST /stop`, which cuts torque like a Ctrl+C) so a pour fires instantly with no
  model-load wait.

## Results & honest limitations

The policy learns the gross pour motion, but it is **not yet reliable** — and that's the
expected outcome, because **60 demonstrations is far too few**. For a contact-rich,
multi-step, multi-object task like this, robust real-world SmolVLA fine-tuning realistically
needs **300+ episodes** (ideally with an additional fixed overhead camera). 60 was simply
what we could teleoperate within the hackathon window.

Other known limits:
- **Single wrist camera** makes it hard for the policy to localize the glasses *before*
  grasping — a fixed overhead view would materially help.
- No success/failure labelling during eval rollouts.

## What's next: HG-DAgger (planned, not run)

The highest-leverage next step is **HG-DAgger** (human-gated DAgger): run the policy, take
over with the leader arm *exactly* when it's about to fail, record those corrections,
aggregate them with the original demos, and fine-tune. This collects data on the policy's
actual failure states — far more sample-efficient than collecting more blind demos toward
that 300+ target.

`hg_dagger.py` / `hg_dagger.sh` implement the gated loop (policy drives; press `i` to take
over with the leader; only the correction frames are recorded). **We built it but ran out
of time to run it** at the hackathon — it's the planned next iteration.

## Repo layout

| Path | What |
|---|---|
| `teleop/` | networked leader↔follower teleoperation (TCP) |
| `record_pour.{sh,py}` | data collection + rerun gripper-target overlay |
| `train_smolvla.sh`, `train_act.sh` | cloud fine-tuning (SmolVLA / ACT) |
| `deploy_pour.sh`, `deploy_infer.py` | run the trained policy on the arm |
| `cocktail_server.{sh,py}` | preloaded HTTP trigger for an instant pour |
| `hg_dagger.{sh,py}` | planned HG-DAgger correction loop |

## Hardware / stack

SO-101 (Feetech STS3215 servos) · LeRobot 0.4.4 · SmolVLA · Mac (MPS) for teleop + deploy ·
cloud H100 for training.

> The dataset and the ~900 MB trained checkpoint are not committed (size) — retrain with
> the scripts above to reproduce.
