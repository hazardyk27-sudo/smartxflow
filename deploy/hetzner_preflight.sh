#!/usr/bin/env bash
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/smartxflow}"
EXPECTED_SHA="${1:-${EXPECTED_SHA:-}}"
EXPECTED_BRANCH="${EXPECTED_BRANCH:-main}"
EXPECTED_DOMAIN="${EXPECTED_DOMAIN:-smartxflow.com}"
EXPECTED_PUBLIC_IP="${EXPECTED_PUBLIC_IP:-91.99.6.245}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

FAILURES=0
WARNINGS=0

pass() { printf 'PASS: %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf 'FAIL: %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

section() {
  printf '\n=== %s ===\n' "$*"
}

is_sha40() {
  [[ "$1" =~ ^[0-9a-fA-F]{40}$ ]]
}

read_env_value() {
  local key="$1"
  local line
  line="$(grep -m1 -E "^${key}=" "$ENV_FILE" 2>/dev/null || true)"
  if [ -z "$line" ]; then
    return 1
  fi
  printf '%s' "${line#*=}"
}

check_env_key() {
  local key="$1"
  local value
  if ! value="$(read_env_value "$key")"; then
    fail "env key missing: $key"
    return
  fi
  if [ -z "${value//[[:space:]]/}" ]; then
    fail "env key empty: $key"
    return
  fi
  case "$value" in
    YOUR_*|your-*|GUCLU_RASTGELE_*|replace-with-*|*YOUR_PROJECT*)
      fail "env key still contains template placeholder: $key"
      ;;
    *) pass "env key present: $key" ;;
  esac
}

check_unit_file_matches() {
  local unit="$1"
  local tracked="$2"
  local installed="$SYSTEMD_DIR/$unit"
  if [ ! -f "$tracked" ]; then
    fail "tracked unit missing: $tracked"
    return
  fi
  if [ ! -f "$installed" ]; then
    fail "installed unit missing: $installed"
    return
  fi
  if cmp -s "$tracked" "$installed"; then
    pass "$unit installed file matches tracked source"
  else
    fail "$unit installed file differs from tracked source"
  fi
}

check_enabled_active() {
  local unit="$1"
  local enabled active
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  active="$(systemctl is-active "$unit" 2>/dev/null || true)"
  if [ "$enabled" = "enabled" ]; then
    pass "$unit enabled at boot"
  else
    fail "$unit not enabled at boot (state=${enabled:-unknown})"
  fi
  if [ "$active" = "active" ]; then
    pass "$unit active"
  else
    fail "$unit not active (state=${active:-unknown})"
  fi
}

check_exec_contains() {
  local unit="$1"
  local expected="$2"
  local exec_line
  exec_line="$(systemctl show -p ExecStart --value "$unit" 2>/dev/null || true)"
  if [[ "$exec_line" == *"$expected"* ]]; then
    pass "$unit ExecStart contains $expected"
  else
    fail "$unit wrong ExecStart (expected token: $expected)"
  fi
}

section "IDENTITY"
if ! is_sha40 "$EXPECTED_SHA"; then
  fail "expected exact 40-character SHA as argument or EXPECTED_SHA"
else
  pass "expected SHA format valid"
fi

if [ ! -d "$APP_DIR/.git" ]; then
  fail "git worktree missing at $APP_DIR"
else
  branch="$(git -C "$APP_DIR" branch --show-current 2>/dev/null || true)"
  head="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
  [ "$branch" = "$EXPECTED_BRANCH" ] && pass "branch=$branch" || fail "branch=$branch expected=$EXPECTED_BRANCH"
  if is_sha40 "$EXPECTED_SHA" && [ "$head" = "$EXPECTED_SHA" ]; then
    pass "HEAD matches expected SHA"
  else
    fail "HEAD does not match expected SHA (HEAD=${head:-unknown})"
  fi
  if git -C "$APP_DIR" diff --quiet && git -C "$APP_DIR" diff --cached --quiet; then
    pass "tracked worktree clean"
  else
    fail "tracked worktree dirty"
  fi
fi

section "ENVIRONMENT"
if [ ! -f "$ENV_FILE" ]; then
  fail "production env file missing: $ENV_FILE"
else
  mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)"
  case "$mode" in
    600|640) pass "env permissions restrictive ($mode)" ;;
    *) warn "env permissions are $mode; expected 600 or 640" ;;
  esac
  for key in \
    SUPABASE_URL \
    SUPABASE_ANON_KEY \
    SUPABASE_SERVICE_ROLE_KEY \
    SESSION_SECRET \
    Betwach_api_key \
    LEARNING_ARCHIVE_ACCESS_SECRET \
    SMARTXFLOW_LEARNING_API_BASE_URL; do
    check_env_key "$key"
  done
fi

section "DEPLOY PRIVILEGE"
if [ "$(id -u)" -eq 0 ]; then
  pass "preflight running as root; deploy privilege available"
else
  sudo_policy="$(sudo -n -l 2>/dev/null || true)"
  if [ -z "$sudo_policy" ]; then
    fail "non-interactive sudo policy unavailable for deploy user"
  elif [[ "$sudo_policy" == *"/usr/bin/install"* && "$sudo_policy" == *"/bin/systemctl"* ]]; then
    pass "deploy user exposes explicit install/systemctl sudo capabilities"
  else
    fail "deploy sudo policy does not expose required install/systemctl capabilities"
  fi
  if [[ "$sudo_policy" == *"NOPASSWD: ALL"* ]]; then
    warn "deploy user has broader NOPASSWD: ALL privilege than the tracked least-privilege contract"
  fi
fi

section "TRACKED SYSTEMD CONTRACT"
check_unit_file_matches smartxflow-web.service "$APP_DIR/deploy/systemd/smartxflow-web.service"
check_unit_file_matches smartxflow-scraper.service "$APP_DIR/deploy/systemd/smartxflow-scraper.service"
check_unit_file_matches smartxflow-alarm.service "$APP_DIR/deploy/systemd/smartxflow-alarm.service"
check_unit_file_matches smartxflow-sinyal.service "$APP_DIR/deploy/smartxflow-sinyal.service"
check_unit_file_matches smartxflow-live.service "$APP_DIR/deploy/systemd/smartxflow-live.service"
check_unit_file_matches smartxflow-poly.service "$APP_DIR/deploy/systemd/smartxflow-poly.service"
check_unit_file_matches smartxflow-learning-archive-prematch.service "$APP_DIR/deploy/systemd/smartxflow-learning-archive-prematch.service"
check_unit_file_matches smartxflow-learning-archive-prematch.timer "$APP_DIR/deploy/systemd/smartxflow-learning-archive-prematch.timer"
check_unit_file_matches smartxflow-learning-archive-postmatch.service "$APP_DIR/deploy/systemd/smartxflow-learning-archive-postmatch.service"
check_unit_file_matches smartxflow-learning-archive-postmatch.timer "$APP_DIR/deploy/systemd/smartxflow-learning-archive-postmatch.timer"

section "SERVICE STATE"
for unit in \
  smartxflow-web.service \
  smartxflow-scraper.service \
  smartxflow-alarm.service \
  smartxflow-sinyal.service \
  smartxflow-live.service \
  smartxflow-poly.service \
  smartxflow-learning-archive-prematch.timer \
  smartxflow-learning-archive-postmatch.timer; do
  check_enabled_active "$unit"
done

section "ENTRYPOINT READBACK"
check_exec_contains smartxflow-web.service "gunicorn"
check_exec_contains smartxflow-web.service "app:app"
check_exec_contains smartxflow-scraper.service "prematch_authoritative_runtime.py"
check_exec_contains smartxflow-alarm.service "alarm_engine.py"
check_exec_contains smartxflow-sinyal.service "sinyal_engine_runtime.py"
check_exec_contains smartxflow-live.service "live_scraper.py"
check_exec_contains smartxflow-poly.service "polymarket_scraper.py"

web_env="$(systemctl show -p Environment --value smartxflow-web.service 2>/dev/null || true)"
if [[ "$web_env" == *"SMARTXFLOW_MODE=server"* && "$web_env" == *"DISABLE_SCRAPER=true"* ]]; then
  pass "web environment is server + UI-only"
else
  fail "web environment missing SMARTXFLOW_MODE=server and/or DISABLE_SCRAPER=true"
fi

scraper_env="$(systemctl show -p Environment --value smartxflow-scraper.service 2>/dev/null || true)"
if [[ "$scraper_env" == *"SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=true"* ]]; then
  pass "prematch authoritative flag enforced by systemd"
else
  fail "prematch authoritative flag not enforced by systemd"
fi

section "LOCAL PROCESS DUPLICATION"
for spec in \
  'prematch_authoritative_runtime.py:1' \
  'alarm_engine.py:1' \
  'sinyal_engine_runtime.py:1' \
  'live_scraper.py:1' \
  'polymarket_scraper.py:1'; do
  pattern="${spec%:*}"
  expected="${spec##*:}"
  count="$(pgrep -af "$pattern" 2>/dev/null | grep -v 'hetzner_preflight.sh' | wc -l | tr -d ' ')"
  if [ "$count" = "$expected" ]; then
    pass "$pattern process count=$count"
  else
    fail "$pattern process count=$count expected=$expected"
  fi
done

section "NETWORK / WEB"
if command -v getent >/dev/null 2>&1; then
  dns_ips="$(getent ahostsv4 "$EXPECTED_DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)"
  if printf '%s\n' "$dns_ips" | grep -Fxq "$EXPECTED_PUBLIC_IP"; then
    pass "$EXPECTED_DOMAIN resolves to expected Hetzner IP $EXPECTED_PUBLIC_IP"
  else
    fail "$EXPECTED_DOMAIN does not resolve to expected IP $EXPECTED_PUBLIC_IP"
  fi
else
  warn "getent unavailable; DNS check skipped"
fi

if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | grep -Eq '127\.0\.0\.1:8000\b'; then
    pass "Gunicorn listener present on 127.0.0.1:8000"
  else
    fail "Gunicorn listener missing on 127.0.0.1:8000"
  fi
else
  warn "ss unavailable; local Gunicorn port check skipped"
fi

nginx_state="$(systemctl is-active nginx 2>/dev/null || true)"
[ "$nginx_state" = "active" ] && pass "nginx active" || fail "nginx not active (state=${nginx_state:-unknown})"

if curl -fsS --max-time 15 -o /dev/null "https://$EXPECTED_DOMAIN/"; then
  pass "HTTPS root reachable"
else
  fail "HTTPS root unreachable"
fi

if curl -fsS --max-time 15 -o /dev/null "https://$EXPECTED_DOMAIN/api/status"; then
  pass "public status endpoint reachable"
else
  warn "public /api/status endpoint unavailable or protected"
fi

section "RESULT"
printf 'FAILURES=%d WARNINGS=%d\n' "$FAILURES" "$WARNINGS"
if [ "$FAILURES" -ne 0 ]; then
  echo "HETZNER_PREFLIGHT_FAIL"
  exit 1
fi

echo "HETZNER_PREFLIGHT_OK"
exit 0
