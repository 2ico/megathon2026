#!/usr/bin/env python3
"""SO-101 follower server.

Runs on the machine physically wired to the FOLLOWER (robot) arm — in this
setup, the Windows 11 PC. It owns the follower's serial port, listens for a
leader client over TCP, and applies each incoming joint target to the arm.

Wire format: newline-delimited JSON. Each line is one action dict exactly as
produced by SO101Leader.get_action(), e.g.
    {"shoulder_pan.pos": 12.3, "shoulder_lift.pos": -4.1, ... "gripper.pos": 30.0}

Usage (on the Windows follower machine):
    python follower_server.py --robot-port COM5 --id my_follower
"""

import argparse
import json
import signal
import socket
import sys

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig


def parse_args():
    p = argparse.ArgumentParser(description="SO-101 follower teleoperation server")
    p.add_argument(
        "--robot-port",
        required=True,
        help="Serial port of the follower arm (e.g. COM5 on Windows, "
        "/dev/ttyACM0 on Linux, /dev/cu.usbmodemXXXX on macOS).",
    )
    p.add_argument(
        "--id",
        required=True,
        help="Calibration id for this follower arm (must match the name you "
        "used with lerobot-calibrate on THIS machine).",
    )
    p.add_argument("--host", default="0.0.0.0", help="Interface to bind (default: all).")
    p.add_argument("--tcp-port", type=int, default=5555, help="TCP port to listen on.")
    p.add_argument(
        "--max-relative-target",
        type=float,
        default=None,
        help="Safety cap: max joint move (in calibrated units) per command. "
        "Prevents violent jumps if the leader pose is far from the follower's. "
        "Slightly slower (reads present position each step). Try 5-15 to start; "
        "omit for no cap.",
    )
    return p.parse_args()


def serve_one_client(conn, addr, robot):
    """Stream actions from a single connected client until it disconnects."""
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # low latency for tiny packets
    print(f"[server] client connected: {addr}")
    buf = b""
    n = 0
    with conn:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break  # client closed
            buf += chunk
            # Process every complete newline-terminated JSON line.
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    action = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[server] skipping malformed line: {line[:80]!r}")
                    continue
                robot.send_action(action)
                n += 1
                if n % 200 == 0:
                    print(f"[server] applied {n} actions")
    print(f"[server] client {addr} disconnected (applied {n} actions)")


def main():
    args = parse_args()

    cfg = SO101FollowerConfig(
        port=args.robot_port,
        id=args.id,
        max_relative_target=args.max_relative_target,
    )
    robot = SO101Follower(cfg)

    print(f"[server] connecting to follower arm on {args.robot_port} ...")
    robot.connect()  # calibrate=True: loads existing calibration for --id, else runs it
    if not robot.is_calibrated:
        print("[server] WARNING: arm is not calibrated. Run lerobot-calibrate first.")
    print("[server] follower connected.")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.tcp_port))
    srv.listen(1)
    print(f"[server] listening on {args.host}:{args.tcp_port} — waiting for leader client...")

    def shutdown(*_):
        print("\n[server] shutting down, disabling torque...")
        try:
            robot.disconnect()  # disable_torque_on_disconnect defaults True
        finally:
            srv.close()
            sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        # Accept loop: if a client drops, keep the arm alive and wait for reconnect.
        while True:
            conn, addr = srv.accept()
            try:
                serve_one_client(conn, addr, robot)
            except (ConnectionResetError, BrokenPipeError) as e:
                print(f"[server] connection error: {e}")
            print("[server] waiting for next client...")
    finally:
        shutdown()


if __name__ == "__main__":
    main()
