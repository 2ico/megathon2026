#!/usr/bin/env python3
"""Identify which serial port is which SO-101 arm, by movement.

Read-only: opens every given port WITHOUT calibration, reads raw motor
positions for a few seconds while you move ONE arm by hand, then reports which
port moved the most. Run this, then physically move the LEADER (handle/teleop)
arm during the countdown.

Usage:
    python identify_arms.py --ports /dev/cu.usbmodemAAAA /dev/cu.usbmodemBBBB --seconds 15
"""

import argparse
import time

from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig


def parse_args():
    p = argparse.ArgumentParser(description="Identify SO-101 arms by movement")
    p.add_argument("--ports", nargs="+", required=True, help="Serial ports to probe.")
    p.add_argument("--seconds", type=float, default=15.0, help="Sampling window.")
    return p.parse_args()


def main():
    args = parse_args()

    arms = {}
    for port in args.ports:
        a = SO101Leader(SO101LeaderConfig(port=port, id="identify"))
        a.connect(calibrate=False)  # raw access, no calibration needed
        arms[port] = a
    print(f"[identify] connected to {len(arms)} port(s).")

    # Track min/max raw Present_Position per (port, motor) to measure travel.
    lo = {p: {} for p in arms}
    hi = {p: {} for p in arms}

    print(f"\n>>> MOVE THE LEADER ARM (the handle/teleop arm) NOW for {args.seconds:.0f}s <<<\n")
    t_end = time.perf_counter() + args.seconds
    while time.perf_counter() < t_end:
        for port, a in arms.items():
            pos = a.bus.sync_read("Present_Position", normalize=False)  # raw ticks (no calibration needed)
            for m, v in pos.items():
                lo[port][m] = min(v, lo[port].get(m, v))
                hi[port][m] = max(v, hi[port].get(m, v))
        time.sleep(0.05)

    print("\n[identify] travel per port (max raw range across joints):")
    ranges = {}
    for port in arms:
        per_joint = {m: hi[port][m] - lo[port][m] for m in hi[port]}
        ranges[port] = max(per_joint.values()) if per_joint else 0
        print(f"  {port}: max joint travel = {ranges[port]} ticks")

    moved = max(ranges, key=ranges.get)
    print(f"\n[identify] => The arm you moved is on: {moved}")
    print("    That is your LEADER port (run leader_client.py with it).")
    others = [p for p in arms if p != moved]
    if others:
        print(f"    The other port(s) -> FOLLOWER: {', '.join(others)}")

    for a in arms.values():
        a.disconnect()


if __name__ == "__main__":
    main()
