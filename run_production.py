#!/usr/bin/env python3
"""
SmartXFlow Production Supervisor
- Runs app.py as a managed subprocess
- Auto-restarts on crash with exponential backoff
- Monitors memory usage and triggers GC when needed
- Handles SIGTERM gracefully
- Ensures 7/24 uptime
"""

import subprocess
import sys
import os
import time
import signal
import gc

MAIN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
MAX_MEMORY_MB = 450
MEMORY_CHECK_INTERVAL = 30
MIN_RESTART_DELAY = 2
MAX_RESTART_DELAY = 60
RESTART_DELAY_MULTIPLIER = 1.5

child_proc = None
shutting_down = False


def get_memory_mb():
    try:
        with open(f"/proc/{os.getpid()}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except:
        pass
    return 0


def get_child_memory_mb(pid):
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except:
        pass
    return 0


def get_total_tree_memory(pid):
    total = get_child_memory_mb(pid)
    try:
        children_path = f"/proc/{pid}/task/{pid}/children"
        if os.path.exists(children_path):
            with open(children_path, "r") as f:
                child_pids = f.read().strip().split()
                for cpid in child_pids:
                    if cpid:
                        total += get_total_tree_memory(int(cpid))
    except:
        pass
    return total


def cleanup_handler(signum, frame):
    global shutting_down, child_proc
    shutting_down = True
    print(f"[Supervisor] Signal {signum} received, shutting down gracefully...")
    if child_proc and child_proc.poll() is None:
        child_proc.terminate()
        try:
            child_proc.wait(timeout=15)
            print("[Supervisor] App terminated gracefully")
        except subprocess.TimeoutExpired:
            child_proc.kill()
            print("[Supervisor] App force-killed after timeout")
    sys.exit(0)


def run_app():
    global child_proc
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    child_proc = subprocess.Popen(
        [sys.executable, MAIN_SCRIPT],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    return child_proc


def main():
    global child_proc, shutting_down

    signal.signal(signal.SIGTERM, cleanup_handler)
    signal.signal(signal.SIGINT, cleanup_handler)

    print("=" * 60)
    print("SmartXFlow Production Supervisor")
    print("=" * 60)
    print(f"  Main script: {MAIN_SCRIPT}")
    print(f"  Memory limit: {MAX_MEMORY_MB}MB")
    print(f"  Auto-restart: ENABLED")
    print("=" * 60)

    restart_delay = MIN_RESTART_DELAY
    consecutive_crashes = 0
    last_successful_start = 0

    while not shutting_down:
        print(f"[Supervisor] Starting app... (attempt after {consecutive_crashes} consecutive crashes)")
        last_successful_start = time.time()

        proc = run_app()

        while proc.poll() is None and not shutting_down:
            time.sleep(MEMORY_CHECK_INTERVAL)

            if proc.poll() is not None:
                break

            uptime = time.time() - last_successful_start
            if uptime > 300:
                consecutive_crashes = 0
                restart_delay = MIN_RESTART_DELAY

            try:
                mem = get_total_tree_memory(proc.pid)
                if mem > MAX_MEMORY_MB:
                    print(f"[Supervisor] WARNING: Memory usage {mem:.0f}MB exceeds {MAX_MEMORY_MB}MB limit")
                    print(f"[Supervisor] Restarting app to free memory...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    gc.collect()
                    time.sleep(3)
                    break
            except Exception as e:
                pass

        if shutting_down:
            break

        exit_code = proc.returncode
        uptime = time.time() - last_successful_start

        if exit_code is not None:
            print(f"[Supervisor] App exited with code {exit_code} after {uptime:.0f}s uptime")

            if uptime < 30:
                consecutive_crashes += 1
                restart_delay = min(restart_delay * RESTART_DELAY_MULTIPLIER, MAX_RESTART_DELAY)
            else:
                consecutive_crashes = 0
                restart_delay = MIN_RESTART_DELAY

            gc.collect()

            print(f"[Supervisor] Restarting in {restart_delay:.1f}s... (consecutive crashes: {consecutive_crashes})")
            time.sleep(restart_delay)

    print("[Supervisor] Supervisor shutting down")


if __name__ == "__main__":
    main()
