#!/usr/bin/env python3
"""SO-101 leader client.

Runs on the machine physically wired to the LEADER (teleop) arm — in this
setup, this Mac. It owns the leader's serial port, reads the joint positions
you set by hand, and streams them to the follower server over TCP.

Usage (on this Mac):
    python leader_client.py --teleop-port /dev/cu.usbmodemXXXX --id my_leader \
        --server 192.168.1.50
"""

import argparse
import json
import socket
import sys
import time

from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig


def parse_args():
    p = argparse.ArgumentParser(description="SO-101 leader teleoperation client")
    p.add_argument(
        "--teleop-port",
        required=True,
        help="Serial port of the leader arm (e.g. /dev/cu.usbmodemXXXX on macOS).",
    )
    p.add_argument(
        "--id",
        required=True,
        help="Calibration id for this leader arm (must match the name you used "
        "with lerobot-calibrate on THIS machine).",
    )
    p.add_argument("--server", required=True, help="IP address of the follower server (Windows PC).")
    p.add_argument("--tcp-port", type=int, default=5555, help="Server TCP port.")
    p.add_argument("--fps", type=float, default=30.0, help="Command rate in Hz (default 30).")
    return p.parse_args()


def connect_to_server(host, port, retries=10, delay=1.0):
    """Open a TCP connection, retrying so the client can be started first."""
    for attempt in range(1, retries + 1):
        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"[client] connected to follower server at {host}:{port}")
            return sock
        except OSError as e:
            print(f"[client] connect attempt {attempt}/{retries} failed: {e}")
            time.sleep(delay)
    print("[client] could not reach the server. Is follower_server.py running and the IP correct?")
    sys.exit(1)


def main():
    args = parse_args()
    period = 1.0 / args.fps

    cfg = SO101LeaderConfig(port=args.teleop_port, id=args.id)
    teleop = SO101Leader(cfg)
    print(f"[client] connecting to leader arm on {args.teleop_port} ...")
    teleop.connect()  # loads calibration for --id
    if not teleop.is_calibrated:
        print("[client] WARNING: leader is not calibrated. Run lerobot-calibrate first.")
    print("[client] leader connected.")

    sock = connect_to_server(args.server, args.tcp_port)

    print(f"[client] streaming at {args.fps:.0f} Hz. Move the leader arm — Ctrl+C to stop.")
    n = 0
    try:
        while True:
            t0 = time.perf_counter()
            action = teleop.get_action()  # {"shoulder_pan.pos": float, ...}
            sock.sendall((json.dumps(action) + "\n").encode())
            n += 1
            if n % 200 == 0:
                print(f"[client] sent {n} actions")
            # Maintain the target rate.
            dt = time.perf_counter() - t0
            if dt < period:
                time.sleep(period - dt)
    except KeyboardInterrupt:
        print("\n[client] stopping.")
    except (BrokenPipeError, ConnectionResetError) as e:
        print(f"\n[client] lost connection to server: {e}")
    finally:
        sock.close()
        teleop.disconnect()


if __name__ == "__main__":
    main()
