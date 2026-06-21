#!/usr/bin/env python3
"""Thin wrapper around `lerobot-record` that customizes the rerun display so you
can match the gripper width while teleoperating:

  - hides all the other joints, showing ONLY the gripper time-series
  - draws a thick horizontal TARGET line at GRIP_TARGET (gripper's 0-100 scale)
  - keeps the camera view (auto-detected from the live observation, so the path
    is always correct regardless of how lerobot names the camera entity)

No package edits: it monkeypatches lerobot's rerun helper, then calls the normal
record() entrypoint (which parses the same CLI args we pass through).

Env:
  GRIP_TARGET        gripper opening (0-100) that holds the glass  (default 50)
  GRIP_TARGET_WIDTH  target line thickness                          (default 10)
"""
import os

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

import lerobot.scripts.lerobot_record as rec

GRIP_TARGET = float(os.environ.get("GRIP_TARGET", "50"))
TARGET_WIDTH = float(os.environ.get("GRIP_TARGET_WIDTH", "10"))

# The arm-mounted cam occasionally delivers frames slowly; relax the staleness
# tolerance (default 500ms) so a transient slow frame doesn't abort recording.
MAX_FRAME_AGE_MS = int(os.environ.get("MAX_FRAME_AGE_MS", "2000"))
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
_orig_read_latest = OpenCVCamera.read_latest
def _read_latest(self, max_age_ms: int = MAX_FRAME_AGE_MS):
    return _orig_read_latest(self, max_age_ms=max_age_ms)
OpenCVCamera.read_latest = _read_latest

# Entity paths: lerobot logs each scalar as "observation.<motor>.pos" / "action.<motor>.pos".
GRIPPER = "/observation.gripper.pos"
GRIPPER_CMD = "/action.gripper.pos"
TARGET = "/observation.gripper.target"


def _blueprint(camera_path):
    gripper_view = rrb.TimeSeriesView(
        name=f"gripper width  (target={GRIP_TARGET:g})",
        contents=[f"+ {GRIPPER}", f"+ {TARGET}", f"+ {GRIPPER_CMD}"],
        # Pin the Y axis so the constant target line stays put (no auto-rescale).
        axis_y=rrb.ScalarAxis(range=(0, 100), zoom_lock=True),
    )
    if camera_path:
        layout = rrb.Vertical(
            rrb.Spatial2DView(name="camera", origin=camera_path),
            gripper_view,
            row_shares=[2, 1],
        )
    else:
        layout = gripper_view
    return rrb.Blueprint(layout, collapse_panels=True)


def _camera_entity(observation):
    """Find the camera entity path from the live observation (first image array)."""
    for k, v in (observation or {}).items():
        if isinstance(v, np.ndarray) and v.ndim >= 2:
            name = k if str(k).startswith("observation.") else f"observation.{k}"
            return "/" + name
    return None


# On the first frame we know the real observation keys, so build + send the
# blueprint then (camera path can't be guessed wrong this way).
_bp_sent = False
_orig_log = rec.log_rerun_data
def log_rerun_data(observation=None, action=None, compress_images=False):
    global _bp_sent
    if not _bp_sent:
        cam = _camera_entity(observation)
        rr.send_blueprint(_blueprint(cam))
        # Static styling: thick red target line so it's an obvious reference.
        rr.log(TARGET.lstrip("/"),
               rr.SeriesLines(widths=TARGET_WIDTH, colors=[255, 60, 60], names="target"),
               static=True)
        print(f"[record_pour] rerun camera entity = {cam}")
        _bp_sent = True
    _orig_log(observation=observation, action=action, compress_images=compress_images)
    rr.log(TARGET.lstrip("/"), rr.Scalars(GRIP_TARGET))  # constant target line
rec.log_rerun_data = log_rerun_data


if __name__ == "__main__":
    rec.record()  # @parser.wrap() reads sys.argv — same flags as lerobot-record
