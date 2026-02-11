#!/bin/bash

start_scraper() {
    python scheduled_scraper.py &
    SCRAPER_PID=$!
    echo "[Supervisor] Scraper started (PID: $SCRAPER_PID)"
}

start_alarm() {
    python alarm_engine.py &
    ALARM_PID=$!
    echo "[Supervisor] Alarm Engine started (PID: $ALARM_PID)"
}

start_web() {
    python app.py &
    WEB_PID=$!
    echo "[Supervisor] Web started (PID: $WEB_PID)"
}

echo "============================================"
echo "SmartXFlow Service Supervisor"
echo "$(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

start_scraper
start_alarm
start_web

echo "[Supervisor] All services running"
echo "[Supervisor] Monitoring every 10 seconds..."

while true; do
    sleep 10

    if ! kill -0 $SCRAPER_PID 2>/dev/null; then
        echo "[Supervisor] $(date '+%H:%M:%S') Scraper crashed! Restarting..."
        start_scraper
    fi

    if ! kill -0 $ALARM_PID 2>/dev/null; then
        echo "[Supervisor] $(date '+%H:%M:%S') Alarm Engine crashed! Restarting..."
        start_alarm
    fi

    if ! kill -0 $WEB_PID 2>/dev/null; then
        echo "[Supervisor] $(date '+%H:%M:%S') Web crashed! Restarting..."
        start_web
    fi
done
