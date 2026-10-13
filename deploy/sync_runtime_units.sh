#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/smartxflow}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo -n "$@"
  fi
}

required=(
  "$APP_DIR/deploy/systemd/smartxflow-web.service"
  "$APP_DIR/deploy/systemd/smartxflow-scraper.service"
  "$APP_DIR/deploy/systemd/smartxflow-alarm.service"
  "$APP_DIR/deploy/systemd/smartxflow-live.service"
  "$APP_DIR/deploy/systemd/smartxflow-poly.service"
  "$APP_DIR/deploy/smartxflow-sinyal.service"
  "$APP_DIR/deploy/systemd/smartxflow-learning-archive-prematch.service"
  "$APP_DIR/deploy/systemd/smartxflow-learning-archive-prematch.timer"
  "$APP_DIR/deploy/systemd/smartxflow-learning-archive-postmatch.service"
  "$APP_DIR/deploy/systemd/smartxflow-learning-archive-postmatch.timer"
)

for path in "${required[@]}"; do
  if [ ! -f "$path" ]; then
    echo "UNIT SYNC STOP: missing tracked unit $path" >&2
    exit 1
  fi
done

# Never elevate an arbitrary shell. Each privileged operation is explicit and
# non-interactive so missing sudo policy fails closed rather than hanging.
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-web.service" "$SYSTEMD_DIR/smartxflow-web.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-scraper.service" "$SYSTEMD_DIR/smartxflow-scraper.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-alarm.service" "$SYSTEMD_DIR/smartxflow-alarm.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-live.service" "$SYSTEMD_DIR/smartxflow-live.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-poly.service" "$SYSTEMD_DIR/smartxflow-poly.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/smartxflow-sinyal.service" "$SYSTEMD_DIR/smartxflow-sinyal.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-learning-archive-prematch.service" "$SYSTEMD_DIR/smartxflow-learning-archive-prematch.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-learning-archive-prematch.timer" "$SYSTEMD_DIR/smartxflow-learning-archive-prematch.timer"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-learning-archive-postmatch.service" "$SYSTEMD_DIR/smartxflow-learning-archive-postmatch.service"
as_root /usr/bin/install -m 0644 "$APP_DIR/deploy/systemd/smartxflow-learning-archive-postmatch.timer" "$SYSTEMD_DIR/smartxflow-learning-archive-postmatch.timer"

as_root /bin/systemctl daemon-reload
as_root /bin/systemctl enable \
  smartxflow-web.service \
  smartxflow-scraper.service \
  smartxflow-alarm.service \
  smartxflow-sinyal.service \
  smartxflow-live.service \
  smartxflow-poly.service \
  smartxflow-learning-archive-prematch.timer \
  smartxflow-learning-archive-postmatch.timer

echo "UNIT_SYNC_OK"
