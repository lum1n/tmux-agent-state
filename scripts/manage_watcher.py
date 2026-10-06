#!/usr/bin/env python3
"""Keep one current watcher daemon per tmux server."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def fingerprint(watcher: Path, scripts: Path) -> str:
    files = set(watcher.parent.rglob("*.py"))
    files.add(watcher)
    files.update(scripts / name for name in (
        "apply_tmux.py", "manage_watcher.py", "run-watcher.sh", "utils/tmux.sh",
    ))
    digest = hashlib.sha256()
    digest.update(str(watcher).encode())
    for path in sorted(files):
        digest.update(str(path).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def process_identity(pid: int) -> str | None:
    if pid <= 1:
        return None
    result = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "uid=,lstart=,stat=,command="],
        capture_output=True, text=True, check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("could not inspect watcher process")
    parts = result.stdout.strip().split(maxsplit=7)
    if len(parts) != 8 or parts[0] != str(os.getuid()) or "Z" in parts[6]:
        return None
    # macOS Python launchers can replace argv[0] after exec; script arguments
    # and process start time remain stable.
    command = parts[7]
    if " -u " in command:
        command = command.split(" -u ", 1)[1]
    return " ".join(parts[:6]) + " " + command


def watcher_children(pid: int, socket: str) -> dict[int, str]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, check=True,
    )
    children = {}
    for line in result.stdout.splitlines():
        child, parent = map(int, line.split())
        if parent != pid:
            continue
        identity = process_identity(child)
        if identity and identity.endswith(f" --listen {socket}.agent-watcher.sock"):
            children[child] = identity
    return children


def stop_daemon(pid: int, identity: str, socket: str) -> None:
    # Older adapters do not handle SIGTERM, so track their classifier too.
    processes = watcher_children(pid, socket)
    processes[pid] = identity
    for number, expected in processes.items():
        if process_identity(number) == expected:
            try:
                os.kill(number, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 3
    while processes and time.monotonic() < deadline:
        processes = {
            number: expected for number, expected in processes.items()
            if process_identity(number) == expected
        }
        if processes:
            time.sleep(0.05)
    for number, expected in processes.items():
        if process_identity(number) == expected:
            try:
                os.kill(number, signal.SIGKILL)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 2
    while any(process_identity(number) == expected for number, expected in processes.items()):
        if time.monotonic() >= deadline:
            raise RuntimeError("old watcher did not exit; refusing to start a duplicate")
        time.sleep(0.05)


def ensure_running(watcher: Path, socket: str, scripts: Path) -> None:
    pidfile = Path(socket + ".agent-state.pid")
    statefile = Path(socket + ".agent-state.state")
    lockfile = Path(socket + ".agent-state.start.lock")
    # flock releases on exit, including crashes; never remove an active lock.
    with lockfile.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        current = fingerprint(watcher, scripts)
        try:
            pid = int(pidfile.read_text().strip())
        except FileNotFoundError:
            pid = 0
        except ValueError:
            print("invalid watcher pid file; replacing it", file=sys.stderr)
            pid = 0
        identity = process_identity(pid)
        if identity and (
            "/apply_tmux.py --watcher " not in identity
            or not identity.endswith(f" --socket {socket}")
        ):
            print("stale watcher pid belongs to another process; leaving it alone", file=sys.stderr)
            identity = None
        try:
            state = json.loads(statefile.read_text())
        except FileNotFoundError:
            state = {}
        except json.JSONDecodeError:
            print("invalid watcher state file; restarting daemon", file=sys.stderr)
            state = {}
        if not isinstance(state, dict):
            print("invalid watcher state file; restarting daemon", file=sys.stderr)
            state = {}
        if identity and state == {"pid": pid, "fingerprint": current, "identity": identity}:
            return
        if identity:
            print("watcher code/configuration changed; restarting daemon", file=sys.stderr)
            stop_daemon(pid, identity, socket)
        with Path(socket + ".agent-state.log").open("a") as log:
            proc = subprocess.Popen(
                [sys.executable, "-u", str(scripts / "apply_tmux.py"),
                 "--watcher", str(watcher), "--socket", socket],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True,
            )
        identity = process_identity(proc.pid)
        if identity is None or proc.poll() is not None:
            raise RuntimeError("watcher failed to start; see agent-state.log")
        pidfile.write_text(str(proc.pid) + "\n")
        statefile.write_text(json.dumps({
            "pid": proc.pid, "fingerprint": current, "identity": identity,
        }) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watcher", required=True, type=Path)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    try:
        ensure_running(args.watcher.resolve(), args.socket, Path(__file__).resolve().parent)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"watcher lifecycle failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
