#!/usr/bin/env python3
"""Minimal wrapper for policy rollout: relaxes the OpenCV camera staleness limit
so a flaky arm cam (or slow MPS inference widening the loop) doesn't abort the run,
then calls lerobot's record() with the same CLI args.

MAX_FRAME_AGE_MS (env): max age of a camera frame before erroring (default 3000).
"""
import os

from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
import lerobot.scripts.lerobot_record as rec

MAX_FRAME_AGE_MS = int(os.environ.get("MAX_FRAME_AGE_MS", "3000"))
_orig_read_latest = OpenCVCamera.read_latest
def _read_latest(self, max_age_ms: int = MAX_FRAME_AGE_MS):
    return _orig_read_latest(self, max_age_ms=max_age_ms)
OpenCVCamera.read_latest = _read_latest

if __name__ == "__main__":
    rec.record()  # same flags as lerobot-record
