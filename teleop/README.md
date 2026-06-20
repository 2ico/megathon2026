# SO-101 networked teleoperation (leader ↔ follower over the network)

Split the standard single-machine `lerobot-teleoperate` across two computers. The setup is
**role-agnostic and OS-agnostic** — any machine (macOS / Windows / Linux) can play either role:

```
  ┌──────────────────────────┐         TCP (JSON joint targets)         ┌──────────────────────────┐
  │  CLIENT machine           │  ───────────────────────────────────▶   │  SERVER machine            │
  │  LEADER / teleop arm       │                                          │  FOLLOWER / robot arm      │
  │  leader_client.py          │                                          │  follower_server.py        │
  └──────────────────────────┘                                          └──────────────────────────┘
```

- The **leader** is the arm you move by hand → runs `leader_client.py` (the client).
- The **follower** is the robot arm that mirrors it → runs `follower_server.py` (the server).
- Either role can run on macOS, Windows, or Linux. The scripts are identical across platforms;
  only the serial-port string differs (`/dev/cu.usbmodem…` on macOS, `COM5` on Windows,
  `/dev/ttyACM0` on Linux).

> **Your current plan:** the **Mac is the leader (client)** and the **Windows 11 PC is the
> follower (server)**. Commands below show that pairing as the concrete example — swap the
> machines/ports freely if you change your mind.

Each arm must be **calibrated on the machine it's physically plugged into.** Calibration files
are per-machine (under `~/.cache/huggingface/lerobot/calibration/`), so calibrate the follower
on its machine and the leader on its machine.

---

## 0. Install LeRobot on BOTH machines (in a venv)

Run the matching install script on each machine. Each creates a Python 3.11 venv at the repo
root (`.venv`) and installs `lerobot[feetech]`. (Python 3.10–3.12 are fine; 3.14 has no torch
wheels yet.)

**macOS / Linux:**
```bash
bash teleop/install_mac.sh
source .venv/bin/activate
```

**Windows 11 (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File teleop\install_windows.ps1
.\.venv\Scripts\Activate.ps1
```

Copy the `teleop/` folder (these scripts) to both machines.

> On this Mac the venv is already created and `lerobot[feetech]` 0.4.4 is installed — just
> `source .venv/bin/activate`.

---

## 1. Put one arm on each machine

Both arms are currently on the Mac. Decide the pairing (your plan: leader → Mac, follower →
Windows), then physically unplug the **follower (robot)** arm and plug it into the other machine.

> The two SO-101 boards are indistinguishable by name (both report "USB Single Serial"); they
> only differ by serial number (`5B14029659`, `5B14032099`). Use the unplug test below to tell
> which is which.

---

## 2. Find each arm's serial port

Run on **each** machine, with the venv active and only that machine's arm plugged in:
```bash
lerobot-find-port
```
It tells you to unplug the arm to reveal the port.
- macOS example: `/dev/cu.usbmodem5B14029659`
- Windows example: `COM5`
- Linux example: `/dev/ttyACM0`

---

## 3. Calibrate each arm (once per machine)

Use whichever role that machine holds. Pick a memorable `--id` per arm and reuse it in step 5/6.

**Follower machine** (your plan: Windows):
```powershell
lerobot-calibrate --robot.type=so101_follower --robot.port=COM5 --robot.id=my_follower
```

**Leader machine** (your plan: Mac):
```bash
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/cu.usbmodem5B14029659 --teleop.id=my_leader
```
Follow the on-screen prompts (move each joint through its full range).

> macOS may prompt for keyboard/Input Monitoring permission for the Terminal — allow it.

---

## 4. Network — find the SERVER's IP & confirm reachability

The **server (follower) machine** must be reachable from the **client (leader) machine**.

**Find the server's LAN IP** (run on the follower machine):
```powershell
ipconfig          # Windows: look for "IPv4 Address" on the active adapter, e.g. 192.168.1.50
```
```bash
ifconfig | grep "inet "   # macOS/Linux follower: pick the 192.168.x / 10.x address
```

**From the client machine, confirm reachability:**
```bash
ping 192.168.1.50
```
- ✅ Replies → same LAN; use that IP as `--server` in step 6.
- ❌ No reply → not mutually reachable. Put both on the same Wi-Fi/router, **or** use a tunnel
  like [Tailscale](https://tailscale.com) (install on both, then use the `100.x.x.x` Tailscale
  IP as `--server`).

**If the server runs on Windows:** the first run triggers a Windows Firewall prompt — allow
Python on **Private networks**. (Pre-allow with, in an admin PowerShell:
`New-NetFirewallRule -DisplayName "lerobot" -Direction Inbound -LocalPort 5555 -Protocol TCP -Action Allow`.)

---

## 5. Start the SERVER (the follower machine)

```bash
python teleop/follower_server.py --robot-port COM5 --id my_follower
# optional safety cap on per-step motion (recommended for first runs):  --max-relative-target 10
```
(Use the follower's port/`--id` for that machine; on Windows the path is `teleop\follower_server.py`.)
It connects to the arm, then prints `listening on 0.0.0.0:5555 — waiting for leader client...`

---

## 6. Start the CLIENT (the leader machine)

```bash
python teleop/leader_client.py \
    --teleop-port /dev/cu.usbmodem5B14029659 \
    --id my_leader \
    --server 192.168.1.50          # the server's IP from step 4
# optional: --fps 60   (default 30)
```

Now move the leader arm — the follower mirrors it. `Ctrl+C` on either side to stop; the server
disables follower torque on exit and waits for the client to reconnect.

---

## Notes & tuning

- **Order:** the client retries the connection for ~10s, so you can start either side first.
- **Latency:** TCP with `TCP_NODELAY` on a LAN is sub-millisecond for these tiny 6-float
  payloads. 30 Hz is smooth; bump `--fps` to 60 for crisper tracking.
- **Safety:** `--max-relative-target N` on the server clips how far the follower moves per
  command, preventing a violent lunge if the leader's pose is far from the follower's at startup.
  It reads present position each step (slightly slower). Start with `10`.
- **No cameras here:** this is pure joint teleoperation. To record datasets/train, add the
  follower's `get_observation()` (and cameras) into the loop — out of scope for this setup.
- **Across the internet (not same LAN):** use Tailscale (easiest) or a VPN/port-forward, then
  pass the reachable IP as `--server`. Expect higher latency.
