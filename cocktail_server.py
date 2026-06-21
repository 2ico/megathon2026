#!/usr/bin/env python3
"""Preloaded SmolVLA cocktail server.

Loads the policy (SmolVLA + VLM backbone) and connects the SO-101 ONCE at startup
— the slow part — then serves POST /make_cocktail which runs ONE pour using the
already-warm model. So the voice agent's tool call fires the pour instantly with no
model-load wait.

Run:      python cocktail_server.py        (or bash cocktail_server.sh)
Trigger:  curl -X POST http://localhost:8088/make_cocktail
Health:   curl http://localhost:8088/health
"""
import json
import os
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Relax flaky-cam staleness BEFORE any camera read (same as deploy_infer).
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
_MAXAGE = int(os.environ.get("MAX_FRAME_AGE_MS", "3000"))
_orig_rl = OpenCVCamera.read_latest
OpenCVCamera.read_latest = lambda self, max_age_ms=_MAXAGE: _orig_rl(self, max_age_ms=max_age_ms)

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies.factory import make_policy, make_pre_post_processors
from lerobot.policies.utils import make_robot_action
from lerobot.processor import make_default_processors
from lerobot.processor.rename_processor import rename_stats
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.pipeline_features import aggregate_pipeline_dataset_features, create_initial_features
from lerobot.datasets.utils import build_dataset_frame, combine_feature_dicts
from lerobot.utils.constants import OBS_STR
from lerobot.utils.control_utils import predict_action
from lerobot.utils.utils import get_safe_torch_device
from lerobot.utils.robot_utils import precise_sleep

PROMPT = "pour the right shot glass into the large plastic cup, then pour the left shot glass into the large plastic cup"
FOLLOWER_PORT = os.environ.get("FOLLOWER_PORT", "/dev/cu.usbmodem5B140320991")
CAM_INDEX = int(os.environ.get("CAM_INDEX", "0"))
CKPT = os.environ.get("CKPT", "./policy_cuda_libre")
DEVICE = os.environ.get("DEVICE", "mps")
FPS = int(os.environ.get("FPS", "15"))
POUR_SECONDS = float(os.environ.get("POUR_SECONDS", "55"))
PORT = int(os.environ.get("PORT", "8088"))

S = {}                      # warm components, filled by setup()
LOCK = threading.Lock()     # one pour at a time
STOP = threading.Event()    # set by POST /stop to abort the current pour


def setup():
    cam = {"camera1": OpenCVCameraConfig(index_or_path=CAM_INDEX, width=640, height=480, fps=FPS)}
    robot = SO101Follower(SO101FollowerConfig(port=FOLLOWER_PORT, id="my_follower", cameras=cam))
    tap, rap, rop = make_default_processors()
    features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=tap, initial_features=create_initial_features(action=robot.action_features), use_videos=True),
        aggregate_pipeline_dataset_features(
            pipeline=rop, initial_features=create_initial_features(observation=robot.observation_features), use_videos=True),
    )
    # throwaway dataset just for meta/features/stats (temp dir -> no cache collision, never recorded)
    meta_root = os.path.join(tempfile.gettempdir(), f"cocktail_meta_{uuid.uuid4().hex}")  # must NOT pre-exist
    ds = LeRobotDataset.create("duico/_cocktail_meta", FPS, root=meta_root,
                               robot_type=robot.name, features=features, use_videos=True,
                               image_writer_processes=0, image_writer_threads=1)
    pcfg = PreTrainedConfig.from_pretrained(CKPT)
    pcfg.pretrained_path = CKPT
    pcfg.device = DEVICE
    policy = make_policy(pcfg, ds_meta=ds.meta)
    pre, post = make_pre_post_processors(
        policy_cfg=pcfg, pretrained_path=CKPT,
        dataset_stats=rename_stats(ds.meta.stats, {}),
        preprocessor_overrides={"device_processor": {"device": DEVICE},
                                "rename_observations_processor": {"rename_map": {}}},
    )
    device = get_safe_torch_device(pcfg.device)
    robot.connect()

    S.update(robot=robot, rap=rap, rop=rop, features=ds.features, policy=policy,
             pre=pre, post=post, device=device, use_amp=pcfg.use_amp, robot_type=robot.robot_type)

    # warm up MPS with one real inference so the FIRST drink isn't slow either
    obs = robot.get_observation()
    of = build_dataset_frame(ds.features, rop(obs), prefix=OBS_STR)
    predict_action(observation=of, policy=policy, device=device, preprocessor=pre, postprocessor=post,
                   use_amp=pcfg.use_amp, task=PROMPT, robot_type=robot.robot_type)
    print("=== model preloaded + robot connected + MPS warmed — READY ===", flush=True)


def make_cocktail():
    """Run one pour with the warm policy. Holds LOCK so calls don't overlap."""
    with LOCK:
        STOP.clear()
        S["robot"].bus.enable_torque()   # re-power in case a prior /stop cut torque
        S["policy"].reset()
        t_end = time.perf_counter() + POUR_SECONDS
        while time.perf_counter() < t_end and not STOP.is_set():
            t0 = time.perf_counter()
            obs = S["robot"].get_observation()
            of = build_dataset_frame(S["features"], S["rop"](obs), prefix=OBS_STR)
            av = predict_action(observation=of, policy=S["policy"], device=S["device"],
                                preprocessor=S["pre"], postprocessor=S["post"], use_amp=S["use_amp"],
                                task=PROMPT, robot_type=S["robot_type"])
            ap = make_robot_action(av, S["features"])
            S["robot"].send_action(S["rap"]((ap, obs)))
            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))
        print("[make_cocktail] " + ("ABORTED" if STOP.is_set() else "pour complete"), flush=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        if self.path.rstrip("/") == "/make_cocktail":
            if LOCK.locked():
                return self._send(409, {"status": "busy", "message": "already making a drink"})
            threading.Thread(target=make_cocktail, daemon=True).start()
            return self._send(200, {"status": "making", "drink": "cuda libre"})
        if self.path.rstrip("/") == "/stop":
            STOP.set()                       # halt the control loop
            try:
                S["robot"].bus.disable_torque()   # cut power — arm goes limp (like Ctrl+C disconnect)
            except Exception as e:
                print("[stop] disable_torque error:", e, flush=True)
            return self._send(200, {"status": "stopped", "torque": "off"})
        self._send(404, {"error": "not found"})

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            return self._send(200, {"ready": bool(S), "busy": LOCK.locked()})
        self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    setup()
    print(f"serving on http://localhost:{PORT}   (POST /make_cocktail)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
