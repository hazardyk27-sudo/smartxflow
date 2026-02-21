import subprocess
import sys
import os
import signal
import time

processes = []

def cleanup(signum, frame):
    for p in processes:
        try:
            p.terminate()
        except:
            pass
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

scraper = subprocess.Popen([sys.executable, "scheduled_scraper.py"])
processes.append(scraper)

alarm = subprocess.Popen([sys.executable, "alarm_engine.py"])
processes.append(alarm)

os.execv(sys.executable, [sys.executable, "app.py"])
