#!/bin/bash
# SmartXFlow Hetzner Update Script
# Usage: update
# Pulls latest code from GitHub and restarts the scraper.

set -e

REPO_DIR="/root/smartxflow"
SCRAPER_DIR="$REPO_DIR/desktop/scraper_standalone"
VENV="$SCRAPER_DIR/venv"
LOG="/var/log/smartxflow_scraper.log"
SCRAPER_SCRIPT="standalone_scraper.py"

echo "[update] Kod cekiliyor..."
cd "$REPO_DIR"
git pull origin main

echo "[update] Bagimliliklar kontrol ediliyor..."
source "$VENV/bin/activate"
pip install -q -r "$SCRAPER_DIR/requirements.txt"

echo "[update] Eski scraper durduruluyor..."
pkill -f "$SCRAPER_SCRIPT" 2>/dev/null && sleep 2 || echo "[update] Calisan scraper bulunamadi, devam ediliyor."

echo "[update] Scraper yeniden baslatiliyor..."
cd "$SCRAPER_DIR"
nohup python3 "$SCRAPER_SCRIPT" > "$LOG" 2>&1 &
NEW_PID=$!

sleep 2
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "[update] Scraper baslatildi (PID: $NEW_PID)"
    echo "[update] Log: tail -f $LOG"
else
    echo "[update] HATA: Scraper baslatilamadi! Log kontrol edin: $LOG"
    exit 1
fi
