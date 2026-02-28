#!/usr/bin/env python3
"""
SmartXFlow Production Supervisor
- Runs app.py as a managed subprocess
- Auto-restarts on crash with exponential backoff
- Monitors memory usage and triggers GC when needed
- HTTP health check detects frozen/hung processes
- Handles SIGTERM gracefully
- Ensures 7/24 uptime
"""

import subprocess
import sys
import os
import time
import signal
import gc

os.environ["PYTHONUNBUFFERED"] = "1"

MAIN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
MAX_MEMORY_MB = 450
CHECK_INTERVAL = 30
HEALTH_CHECK_INTERVAL = 90
HEALTH_CHECK_TIMEOUT = 10
HEALTH_CHECK_FAILURES_BEFORE_RESTART = 3
HEALTH_CHECK_URL = "http://127.0.0.1:5000/health"
MIN_RESTART_DELAY = 2
MAX_RESTART_DELAY = 60
RESTART_DELAY_MULTIPLIER = 1.5
STARTUP_GRACE_PERIOD = 30

child_proc = None
shutting_down = False


def log(msg):
    print(f"[Supervisor] {msg}", flush=True)


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


def check_http_health():
    try:
        import urllib.request
        req = urllib.request.Request(HEALTH_CHECK_URL)
        resp = urllib.request.urlopen(req, timeout=HEALTH_CHECK_TIMEOUT)
        return resp.status == 200
    except:
        return False


def cleanup_handler(signum, frame):
    global shutting_down, child_proc
    shutting_down = True
    log(f"Signal {signum} received, shutting down gracefully...")
    if child_proc and child_proc.poll() is None:
        child_proc.terminate()
        try:
            child_proc.wait(timeout=15)
            log("App terminated gracefully")
        except subprocess.TimeoutExpired:
            child_proc.kill()
            log("App force-killed after timeout")
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

    print("=" * 60, flush=True)
    log("SmartXFlow Production Supervisor STARTED")
    print("=" * 60, flush=True)
    log(f"Main script: {MAIN_SCRIPT}")
    log(f"Memory limit: {MAX_MEMORY_MB}MB")
    log(f"Health check: {HEALTH_CHECK_URL} every {HEALTH_CHECK_INTERVAL}s")
    log(f"Auto-restart: ENABLED")
    print("=" * 60, flush=True)

    restart_delay = MIN_RESTART_DELAY
    consecutive_crashes = 0
    last_successful_start = 0

    while not shutting_down:
        log(f"Starting app... (consecutive crashes: {consecutive_crashes})")
        last_successful_start = time.time()

        proc = run_app()

        health_fail_count = 0
        last_health_check = 0

        while proc.poll() is None and not shutting_down:
            time.sleep(CHECK_INTERVAL)

            if proc.poll() is not None:
                break

            uptime = time.time() - last_successful_start
            if uptime > 300:
                consecutive_crashes = 0
                restart_delay = MIN_RESTART_DELAY

            try:
                mem = get_total_tree_memory(proc.pid)
                if mem > MAX_MEMORY_MB:
                    log(f"WARNING: Memory {mem:.0f}MB > {MAX_MEMORY_MB}MB limit, restarting...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    gc.collect()
                    time.sleep(3)
                    break
            except:
                pass

            now = time.time()
            if uptime > STARTUP_GRACE_PERIOD and (now - last_health_check) >= HEALTH_CHECK_INTERVAL:
                last_health_check = now
                if check_http_health():
                    health_fail_count = 0
                else:
                    health_fail_count += 1
                    log(f"Health check FAILED ({health_fail_count}/{HEALTH_CHECK_FAILURES_BEFORE_RESTART})")
                    if health_fail_count >= HEALTH_CHECK_FAILURES_BEFORE_RESTART:
                        log(f"App unresponsive after {health_fail_count} checks, restarting...")
                        proc.terminate()
                        try:
                            proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        time.sleep(3)
                        break

        if shutting_down:
            break

        exit_code = proc.returncode
        uptime = time.time() - last_successful_start

        if exit_code is not None:
            log(f"App exited with code {exit_code} after {uptime:.0f}s uptime")

            if uptime < 30:
                consecutive_crashes += 1
                restart_delay = min(restart_delay * RESTART_DELAY_MULTIPLIER, MAX_RESTART_DELAY)
            else:
                consecutive_crashes = 0
                restart_delay = MIN_RESTART_DELAY

            gc.collect()

            log(f"Restarting in {restart_delay:.1f}s... (consecutive crashes: {consecutive_crashes})")
            time.sleep(restart_delay)

    log("Supervisor shutting down")


if __name__ == "__main__":
    main()
