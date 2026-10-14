#!/bin/bash
set -euo pipefail

DOMAIN="smartxflow.com"
WWW_DOMAIN="www.smartxflow.com"
EXPECTED_IP="91.99.6.245"
APP_DIR="/opt/smartxflow"
NGINX_CONF="/etc/nginx/sites-available/smartxflow"
NGINX_LINK="/etc/nginx/sites-enabled/smartxflow"
CANONICAL_CONF="$APP_DIR/deploy/nginx-smartxflow.conf"
BACKUP_DIR="/etc/nginx/smartxflow-cutover-backups"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_CONF="$BACKUP_DIR/smartxflow.$TIMESTAMP.conf"
MUTATED=0

log() {
  printf '[web-cutover] %s\n' "$*"
}

fail() {
  log "FAIL: $*"
  exit 1
}

authoritative_nameservers() {
  dig +short NS "$DOMAIN" 2>/dev/null \
    | sed 's/\.$//' \
    | sed '/^$/d' \
    | sort -u
}

resolve_a_at_ns() {
  local ns="$1"
  local host="$2"
  dig +short "@$ns" A "$host" 2>/dev/null \
    | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' \
    | sort -u \
    || true
}

require_authoritative_dns() {
  local host="$1"
  local ns_list ns values
  ns_list="$(authoritative_nameservers)"
  [ -n "$ns_list" ] || fail "could not resolve authoritative nameservers for $DOMAIN"

  while IFS= read -r ns; do
    [ -n "$ns" ] || continue
    values="$(resolve_a_at_ns "$ns" "$host")"
    [ -n "$values" ] || fail "$host has no authoritative A answer from $ns"
    if [ "$values" != "$EXPECTED_IP" ]; then
      log "$host authoritative answer from $ns:"
      printf '%s\n' "$values"
      fail "$host must resolve only to $EXPECTED_IP on every authoritative nameserver before cutover"
    fi
    log "Authoritative DNS OK: $host -> $EXPECTED_IP via $ns"
  done <<< "$ns_list"
}

verify_certificate_file() {
  local host="$1"
  local cert="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
  openssl x509 -in "$cert" -noout -checkhost "$host" >/dev/null \
    || fail "certificate file does not cover $host"
  log "Certificate file covers $host"
}

verify_local_tls() {
  local host="$1"
  local served_cert
  served_cert="$(mktemp)"
  if ! openssl s_client \
      -connect 127.0.0.1:443 \
      -servername "$host" \
      -showcerts \
      </dev/null 2>/dev/null \
      | openssl x509 -outform PEM > "$served_cert"; then
    rm -f "$served_cert"
    fail "could not read local TLS certificate for $host"
  fi
  if ! openssl x509 -in "$served_cert" -noout -checkhost "$host" >/dev/null; then
    log "Local TLS certificate presented for $host:"
    openssl x509 -in "$served_cert" -noout -subject -issuer -ext subjectAltName || true
    rm -f "$served_cert"
    fail "local TLS certificate hostname mismatch for $host"
  fi
  rm -f "$served_cert"
  log "Local TLS certificate covers $host"
}

rollback() {
  local code=$?
  if [ "$code" -eq 0 ] || [ "$MUTATED" -eq 0 ]; then
    exit "$code"
  fi

  log "ERROR detected after nginx mutation; attempting rollback"
  if [ -f "$BACKUP_CONF" ]; then
    cp -a "$BACKUP_CONF" "$NGINX_CONF"
    ln -sfn "$NGINX_CONF" "$NGINX_LINK"
    if nginx -t; then
      systemctl reload nginx || true
      log "Rollback restored $BACKUP_CONF"
    else
      log "Rollback config failed nginx -t; manual intervention required"
    fi
  fi
  exit "$code"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || fail "must run as root"
[ -d "$APP_DIR" ] || fail "$APP_DIR missing"
[ -f "$CANONICAL_CONF" ] || fail "$CANONICAL_CONF missing"
command -v dig >/dev/null 2>&1 || fail "dig is required before cutover"
command -v nginx >/dev/null 2>&1 || fail "nginx is required before cutover"
command -v openssl >/dev/null 2>&1 || fail "openssl is required before cutover"

log "Preflight: authoritative DNS must point both names to Hetzner"
require_authoritative_dns "$DOMAIN"
require_authoritative_dns "$WWW_DOMAIN"

systemctl is-active --quiet smartxflow-web || fail "smartxflow-web is not active"
systemctl is-active --quiet nginx || fail "nginx is not active"
curl --noproxy '*' -fsS --max-time 10 http://127.0.0.1:8000/ >/dev/null \
  || fail "Gunicorn local HTTP check failed"
nginx -t

mkdir -p "$BACKUP_DIR" /var/www/certbot
if [ -f "$NGINX_CONF" ]; then
  cp -a "$NGINX_CONF" "$BACKUP_CONF"
else
  : > "$BACKUP_CONF"
fi
log "Nginx backup: $BACKUP_CONF"

if ! command -v certbot >/dev/null 2>&1; then
  log "Installing Certbot packages"
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q certbot python3-certbot-nginx
fi

cat > "$NGINX_CONF" <<'NGINX_HTTP'
server {
    listen 80;
    listen [::]:80;
    server_name smartxflow.com www.smartxflow.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout    120;
        proxy_connect_timeout 120;
        client_max_body_size  10m;
    }
}
NGINX_HTTP
ln -sfn "$NGINX_CONF" "$NGINX_LINK"
rm -f /etc/nginx/sites-enabled/default
nginx -t
MUTATED=1
systemctl reload nginx

CERTBOT_CONTACT_ARGS=(--register-unsafely-without-email)
if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
  CERTBOT_CONTACT_ARGS=(--email "$LETSENCRYPT_EMAIL")
fi

log "Requesting/renewing Let's Encrypt certificate"
certbot certonly --nginx \
  -d "$DOMAIN" \
  -d "$WWW_DOMAIN" \
  --non-interactive \
  --agree-tos \
  "${CERTBOT_CONTACT_ARGS[@]}"

[ -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] || fail "certificate fullchain missing"
[ -s "/etc/letsencrypt/live/$DOMAIN/privkey.pem" ] || fail "certificate private key missing"
verify_certificate_file "$DOMAIN"
verify_certificate_file "$WWW_DOMAIN"

install -m 0644 "$CANONICAL_CONF" "$NGINX_CONF"
ln -sfn "$NGINX_CONF" "$NGINX_LINK"
nginx -t
systemctl reload nginx

verify_local_tls "$DOMAIN"
verify_local_tls "$WWW_DOMAIN"

curl --noproxy '*' -fsSI --max-time 15 \
  --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" >/dev/null \
  || fail "local HTTPS smoke test failed for $DOMAIN"
curl --noproxy '*' -fsSI --max-time 15 \
  --resolve "$WWW_DOMAIN:443:127.0.0.1" "https://$WWW_DOMAIN/" >/dev/null \
  || fail "local HTTPS smoke test failed for $WWW_DOMAIN"

systemctl is-active --quiet nginx || fail "nginx inactive after cutover"
systemctl is-active --quiet smartxflow-web || fail "smartxflow-web inactive after cutover"

MUTATED=0
trap - EXIT
log "WEB_CUTOVER_OK domain=$DOMAIN ip=$EXPECTED_IP backup=$BACKUP_CONF"
