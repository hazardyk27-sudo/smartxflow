from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "cutover_web_to_hetzner.sh"
NGINX = ROOT / "deploy" / "nginx-smartxflow.conf"


def test_web_cutover_is_fail_closed_before_nginx_mutation():
    text = SCRIPT.read_text(encoding="utf-8")
    apex = text.index('require_authoritative_dns "$DOMAIN"')
    www = text.index('require_authoritative_dns "$WWW_DOMAIN"')
    first_nginx_write = text.index('cat > "$NGINX_CONF"')
    apt_install = text.index('apt-get install')
    assert apex < first_nginx_write
    assert www < first_nginx_write
    assert apex < apt_install
    assert www < apt_install
    assert 'EXPECTED_IP="91.99.6.245"' in text
    assert 'must resolve only to $EXPECTED_IP on every authoritative nameserver before cutover' in text


def test_web_cutover_queries_authoritative_nameservers_directly():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'dig +short NS "$DOMAIN"' in text
    assert 'dig +short "@$ns" A "$host"' in text
    assert 'Authoritative DNS OK:' in text
    assert "grep -E '^[0-9]{1,3}(\\.[0-9]{1,3}){3}$'" in text


def test_web_cutover_has_backup_and_rollback_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'trap rollback EXIT' in text
    assert 'BACKUP_DIR="/etc/nginx/smartxflow-cutover-backups"' in text
    assert 'cp -a "$NGINX_CONF" "$BACKUP_CONF"' in text
    assert 'cp -a "$BACKUP_CONF" "$NGINX_CONF"' in text
    assert 'nginx -t' in text
    assert 'systemctl reload nginx' in text


def test_web_cutover_uses_certonly_then_canonical_nginx():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'certbot certonly --nginx' in text
    assert '--agree-tos' in text
    assert 'install -m 0644 "$CANONICAL_CONF" "$NGINX_CONF"' in text
    assert '/etc/letsencrypt/live/$DOMAIN/fullchain.pem' in text
    assert '/etc/letsencrypt/live/$DOMAIN/privkey.pem' in text
    assert 'certbot --nginx' not in text


def test_web_cutover_verifies_certificate_file_and_direct_local_sni():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'openssl x509 -in "$cert" -noout -checkhost "$host"' in text
    assert '-connect 127.0.0.1:443' in text
    assert '-servername "$host"' in text
    assert 'local TLS certificate hostname mismatch' in text


def test_web_cutover_waits_for_reloaded_nginx_tls_worker():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'wait_for_local_tls()' in text
    assert 'for attempt in $(seq 1 20)' in text
    assert 'sleep 0.5' in text
    assert 'Waiting for reloaded Nginx TLS worker' in text
    assert 'wait_for_local_tls "$DOMAIN"' in text
    assert 'wait_for_local_tls "$WWW_DOMAIN"' in text


def test_web_cutover_verifies_local_https_without_proxy_and_services():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "curl --noproxy '*' -fsSI" in text
    assert '--resolve "$DOMAIN:443:127.0.0.1"' in text
    assert '--resolve "$WWW_DOMAIN:443:127.0.0.1"' in text
    assert 'systemctl is-active --quiet nginx' in text
    assert 'systemctl is-active --quiet smartxflow-web' in text
    assert 'WEB_CUTOVER_OK' in text


def test_canonical_nginx_points_only_to_local_gunicorn():
    text = NGINX.read_text(encoding="utf-8")
    assert 'server_name smartxflow.com www.smartxflow.com;' in text
    assert 'proxy_pass         http://127.0.0.1:8000;' in text
    assert '/etc/letsencrypt/live/smartxflow.com/fullchain.pem' in text
    assert '/etc/letsencrypt/live/smartxflow.com/privkey.pem' in text
    assert 'replit' not in text.lower()
