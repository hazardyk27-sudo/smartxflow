#!/bin/bash
# SmartXFlow — SSL Kurulum Scripti (Let's Encrypt / Certbot)
#
# ÖNKOŞUL: DNS A kaydı 91.99.6.245'e yönlendirilmiş olmalı.
#           Kontrol: dig smartxflow.com +short  → 91.99.6.245 görmeli
#
# KULLANIM: sudo bash deploy/setup_ssl.sh
#           (Sunucuda /opt/smartxflow/deploy/ içindeyken)

set -e

DOMAIN="smartxflow.com"
WWW_DOMAIN="www.smartxflow.com"
EMAIL="admin@smartxflow.com"   # Let's Encrypt bildirim emaili
NGINX_CONF="/etc/nginx/sites-available/smartxflow"
APP_DIR="/opt/smartxflow"

echo "============================================"
echo " SmartXFlow — SSL Kurulum (Let's Encrypt)"
echo " Domain: $DOMAIN"
echo "============================================"
echo ""

# ── 1. DNS kontrolü ─────────────────────────────────────────────────────────
echo "[1/4] DNS kaydı kontrol ediliyor..."
RESOLVED=$(dig +short "$DOMAIN" 2>/dev/null | head -1)
if [ "$RESOLVED" != "91.99.6.245" ]; then
    echo ""
    echo "HATA: $DOMAIN henüz 91.99.6.245'e çözümlenmiyor."
    echo "       Mevcut değer: '${RESOLVED:-BOŞ}'"
    echo ""
    echo "DNS A kaydını domain yönetim panelinizden ayarlayın:"
    echo "  Tip: A   Ad: @    Değer: 91.99.6.245"
    echo "  Tip: A   Ad: www  Değer: 91.99.6.245"
    echo ""
    echo "DNS yayılması 1-24 saat sürebilir. Yeniden deneyin:"
    echo "  sudo bash $APP_DIR/deploy/setup_ssl.sh"
    exit 1
fi
echo "DNS OK — $DOMAIN → $RESOLVED"

# ── 2. Certbot kurulu mu? ────────────────────────────────────────────────────
echo ""
echo "[2/4] Certbot kontrol ediliyor..."
if ! command -v certbot &>/dev/null; then
    echo "Certbot bulunamadı, kuruluyor..."
    apt-get update -q
    apt-get install -y -q certbot python3-certbot-nginx
fi
echo "Certbot hazır: $(certbot --version 2>&1)"

# ── 3. Nginx HTTP-only config'i yerleştir (certbot challenge için) ──────────
echo ""
echo "[3/4] Nginx HTTP konfigürasyonu ayarlanıyor..."
cat > "$NGINX_CONF" << 'NGXEOF'
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
NGXEOF

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/smartxflow
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo "Nginx HTTP konfigürasyonu aktif."

# ── 4. Certbot ile SSL sertifikası al + nginx'i güncelle ────────────────────
echo ""
echo "[4/4] Let's Encrypt sertifikası alınıyor..."
echo "  (--nginx flag'i nginx config'ini otomatik günceller)"
echo ""

certbot --nginx \
    -d "$DOMAIN" \
    -d "$WWW_DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --redirect

# Certbot başarılı olduktan sonra deploy/nginx-smartxflow.conf'u
# tam SSL versiyonuyla güncelle (statik dosya cache + güvenlik başlıkları ekli)
cat > "$NGINX_CONF" << 'NGXEOF'
# SmartXFlow — Nginx (SSL aktif)

server {
    listen 80;
    listen [::]:80;
    server_name smartxflow.com www.smartxflow.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name smartxflow.com www.smartxflow.com;

    ssl_certificate     /etc/letsencrypt/live/smartxflow.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/smartxflow.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options            "SAMEORIGIN"                          always;
    add_header X-Content-Type-Options     "nosniff"                             always;
    add_header Referrer-Policy            "strict-origin-when-cross-origin"     always;

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

    location /static/ {
        alias /opt/smartxflow/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
NGXEOF

nginx -t && systemctl reload nginx
echo ""
echo "============================================"
echo " SSL KURULUM TAMAMLANDI!"
echo "============================================"
echo ""
echo " ✓ https://smartxflow.com     → ÇALIŞIYOR"
echo " ✓ https://www.smartxflow.com → ÇALIŞIYOR"
echo " ✓ HTTP → HTTPS yönlendirme   → AKTİF"
echo " ✓ Sertifika otomatik yenileme:"
echo "   systemctl list-timers | grep certbot"
echo ""
echo " Test için:"
echo "   curl -I http://smartxflow.com   (301 görmeli)"
echo "   curl -I https://smartxflow.com  (200 görmeli)"
echo "============================================"
