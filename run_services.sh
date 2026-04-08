#!/bin/bash

SCRAPER_PID=""
ALARM_PID=""
LIVE_PID=""
UNDERDOG_PID=""

cleanup() {
    echo "[run_services] SIGTERM received, shutting down..."
    [ -n "$SCRAPER_PID" ] && kill $SCRAPER_PID 2>/dev/null
    [ -n "$ALARM_PID" ] && kill $ALARM_PID 2>/dev/null
    [ -n "$LIVE_PID" ] && kill $LIVE_PID 2>/dev/null
    [ -n "$UNDERDOG_PID" ] && kill $UNDERDOG_PID 2>/dev/null
    wait 2>/dev/null
    echo "[run_services] All services stopped."
    exit 0
}

trap cleanup SIGTERM SIGINT

start_scraper() {
    while true; do
        echo "[run_services] $(date '+%H:%M:%S') Starting scheduled_scraper.py..."
        python scheduled_scraper.py
        EXIT_CODE=$?
        echo "[run_services] $(date '+%H:%M:%S') scheduled_scraper.py exited (code=$EXIT_CODE), restarting in 5s..."
        sleep 5
    done
}

start_alarm() {
    while true; do
        echo "[run_services] $(date '+%H:%M:%S') Starting alarm_engine.py..."
        python alarm_engine.py
        EXIT_CODE=$?
        echo "[run_services] $(date '+%H:%M:%S') alarm_engine.py exited (code=$EXIT_CODE), restarting in 5s..."
        sleep 5
    done
}

start_live() {
    while true; do
        echo "[run_services] $(date '+%H:%M:%S') Starting live_scraper.py..."
        python live_scraper.py
        EXIT_CODE=$?
        echo "[run_services] $(date '+%H:%M:%S') live_scraper.py exited (code=$EXIT_CODE), restarting in 5s..."
        sleep 5
    done
}

start_underdog() {
    while true; do
        echo "[run_services] $(date '+%H:%M:%S') Starting underdog_engine.py..."
        python underdog_engine.py
        EXIT_CODE=$?
        echo "[run_services] $(date '+%H:%M:%S') underdog_engine.py exited (code=$EXIT_CODE), restarting in 5s..."
        sleep 5
    done
}

echo "============================================"
echo "[run_services] SmartXFlow Services Supervisor"
echo "[run_services] $(date '+%Y-%m-%d %H:%M:%S')"
echo "[run_services] Scraper + Alarm Engine + Live Scraper + Sinyal Engine (auto-restart)"
echo "============================================"

start_scraper &
SCRAPER_PID=$!

start_alarm &
ALARM_PID=$!

start_live &
LIVE_PID=$!

start_underdog &
UNDERDOG_PID=$!

wait
