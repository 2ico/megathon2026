#!/usr/bin/env python3
"""HG-DAgger for the SO-101 cuda-libre pour policy.

The trained SmolVLA policy drives the follower. When it's about to fail, you press
a key to TAKE OVER with the leader arm; while you're in control, those (observation,
human-action) frames are recorded. Releasing control hands back to the policy.
Only intervention frames are saved -> that's exactly the HG-DAgger correction signal.
Aggregate this dataset with the original demos and fine-tune the checkpoint.

CONTROLS (focus the terminal; macOS needs Accessibility permission):
    i   toggle intervention on/off (leader takes over <-> policy drives)
    n   end current episode + save its intervention frames, go to next
    q   stop the whole session

Env / args: see argparse below. Reuses lerobot's predict_action so SmolVLA inference
(preprocess -> action chunk -> postprocess) matches training.

NOTE: this drives real hardware via internal lerobot APIs — test with the arm clear
on the first run. When you grab the leader to intervene, move it to roughly the
follower's current pose first to avoid a jump (or set --max-rel to clip it).
"""
import argparse
import os
import threading
import time

from pynput import keyboard

# Relax flaky-cam staleness (same as deploy) BEFORE anything reads frames.
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
_MAXAGE = int(os.environ.get("MAX_FRAME_AGE_MS", "3000"))
_orig_rl = OpenCVCamera.read_latest
OpenCVCamera.read_latest = lambda self, max_age_ms=_MAXAGE: _orig_rl(self, max_age_ms=max_age_ms)

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies.factory import make_policy, make_pre_post_processors
from lerobot.policies.utils import make_robot_action
from lerobot.processor import make_default_processors
from lerobot.processor.rename_processor import rename_stats
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.pipeline_features import aggregate_pipeline_dataset_features, create_initial_features
from lerobot.datasets.utils import build_dataset_frame, combine_feature_dicts
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.control_utils import predict_action
from lerobot.utils.utils import get_safe_torch_device
from lerobot.utils.robot_utils import precise_sleep

PROMPT = "pour the right shot glass into the large plastic cup, then pour the left shot glass into the large plastic cup"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--follower-port", default="/dev/cu.usbmodem5B140320991")
    p.add_argument("--leader-port", default="/dev/cu.usbmodem5B140296591")
    p.add_argument("--cam-index", type=int, default=0)
    p.add_argument("--checkpoint", default="./policy_cuda_libre")
    p.add_argument("--repo-id", default="duico/cuda_libre_dagger")
    p.add_argument("--device", default="mps")
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--episodes", type=int, default=20)
    p.add_argument("--max-rel", type=float, default=None, help="clip per-step follower motion (deg) — safety on takeover")
    return p.parse_args()


class Keys:
    """Background keyboard listener for gate / end-episode / stop."""
    def __init__(self):
        self.intervene = False
        self.end_episode = False
        self.stop = False
        self._lock = threading.Lock()
        keyboard.Listener(on_press=self._on).start()

    def _on(self, key):
        try:
            c = key.char
        except AttributeError:
            return
        with self._lock:
            if c == "i":
                self.intervene = not self.intervene
                print(f"\n[gate] intervention {'ON (you drive)' if self.intervene else 'OFF (policy drives)'}")
            elif c == "n":
                self.end_episode = True
            elif c == "q":
                self.stop = True


def main():
    a = parse_args()

    cam = {"camera1": OpenCVCameraConfig(index_or_path=a.cam_index, width=640, height=480, fps=a.fps)}
    robot = SO101Follower(SO101FollowerConfig(
        port=a.follower_port, id="my_follower", cameras=cam, max_relative_target=a.max_rel))
    teleop = SO101Leader(SO101LeaderConfig(port=a.leader_port, id="my_leader"))

    teleop_action_proc, robot_action_proc, robot_obs_proc = make_default_processors()

    features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=teleop_action_proc,
            initial_features=create_initial_features(action=robot.action_features), use_videos=True),
        aggregate_pipeline_dataset_features(
            pipeline=robot_obs_proc,
            initial_features=create_initial_features(observation=robot.observation_features), use_videos=True),
    )

    dataset = LeRobotDataset.create(
        a.repo_id, a.fps, robot_type=robot.name, features=features, use_videos=True,
        image_writer_processes=0, image_writer_threads=4)

    # Load policy + processors exactly like lerobot-record does.
    pcfg = PreTrainedConfig.from_pretrained(a.checkpoint)
    pcfg.pretrained_path = a.checkpoint
    pcfg.device = a.device
    policy = make_policy(pcfg, ds_meta=dataset.meta)
    preproc, postproc = make_pre_post_processors(
        policy_cfg=pcfg, pretrained_path=a.checkpoint,
        dataset_stats=rename_stats(dataset.meta.stats, {}),
        preprocessor_overrides={
            "device_processor": {"device": a.device},
            "rename_observations_processor": {"rename_map": {}},
        },
    )
    device = get_safe_torch_device(pcfg.device)

    robot.connect()
    teleop.connect()
    keys = Keys()
    print("\n=== HG-DAgger ready ===  i=take over/release, n=next episode, q=quit\n")

    try:
        ep = 0
        while ep < a.episodes and not keys.stop:
            print(f"--- episode {ep}: policy driving. Press 'i' to correct, 'n' when done ---")
            policy.reset()
            keys.end_episode = False
            was_intervening = False
            n_frames = 0

            while not keys.end_episode and not keys.stop:
                t0 = time.perf_counter()
                obs = robot.get_observation()
                obs_proc = robot_obs_proc(obs)
                obs_frame = build_dataset_frame(dataset.features, obs_proc, prefix=OBS_STR)

                if keys.intervene:
                    if not was_intervening:
                        print("[gate] you are driving (recording corrections)")
                    act = teleop.get_action()
                    act_proc = teleop_action_proc((act, obs))
                    # record the HUMAN action as the training target
                    act_frame = build_dataset_frame(dataset.features, act_proc, prefix=ACTION)
                    dataset.add_frame({**obs_frame, **act_frame, "task": PROMPT})
                    n_frames += 1
                    to_send = robot_action_proc((act_proc, obs))
                    was_intervening = True
                else:
                    if was_intervening:
                        policy.reset()  # re-plan from the corrected state
                        was_intervening = False
                    action_values = predict_action(
                        observation=obs_frame, policy=policy, device=device,
                        preprocessor=preproc, postprocessor=postproc,
                        use_amp=pcfg.use_amp, task=PROMPT, robot_type=robot.robot_type)
                    act_proc = make_robot_action(action_values, dataset.features)
                    to_send = robot_action_proc((act_proc, obs))

                robot.send_action(to_send)
                precise_sleep(max(1.0 / a.fps - (time.perf_counter() - t0), 0.0))

            # Save only if this episode captured corrections.
            if n_frames > 0:
                dataset.save_episode()
                print(f"[episode {ep}] saved {n_frames} intervention frames")
                ep += 1
            else:
                dataset.clear_episode_buffer()
                print(f"[episode {ep}] no corrections — discarded (not counted)")
    finally:
        robot.disconnect()
        teleop.disconnect()
        print("\nDone. Aggregate this dataset with the original demos and fine-tune the checkpoint.")


if __name__ == "__main__":
    main()
