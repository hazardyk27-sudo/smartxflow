#!/bin/bash
# SmartXFlow — Hetzner CPX22 Tek Seferlik Kurulum Scripti
# Ubuntu 22.04 | Çalıştır: bash setup_hetzner.sh
# Çalıştırmadan önce bu dosyadaki GITHUB_REPO değişkenini kontrol et.

set -e

GITHUB_REPO="https://github.com/hazardyk27-sudo/SmartXFlow.git"
APP_DIR="/opt/smartxflow"
APP_USER="smartxflow"
DOMAIN="smartxflow.com"

echo "============================================"
echo " SmartXFlow — Hetzner Kurulum"
echo " Domain : $DOMAIN"
echo " App Dir: $APP_DIR"
echo "============================================"

# ── 1. Sistem güncellemesi ──────────────────────────────────────────────────
echo ""
echo "[1/9] Sistem güncelleniyor..."
apt-get update -q
apt-get upgrade -y -q
apt-get install -y -q \
    git curl wget ufw \
    nginx certbot python3-certbot-nginx \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    build-essential libssl-dev libffi-dev \
    supervisor

# ── 2. UFW Firewall ────────────────────────────────────────────────────────
echo ""
echo "[2/9] Firewall ayarlanıyor..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment 'SSH'
ufw allow 80/tcp    comment 'HTTP'
ufw allow 443/tcp   comment 'HTTPS'
ufw --force enable
echo "UFW aktif:"
ufw status

# ── 3. Kullanıcı oluştur ───────────────────────────────────────────────────
echo ""
echo "[3/9] Uygulama kullanıcısı oluşturuluyor..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --create-home --home-dir "$APP_DIR" "$APP_USER"
    echo "Kullanıcı oluşturuldu: $APP_USER"
else
    echo "Kullanıcı zaten mevcut: $APP_USER"
fi

# Kullanıcıya systemctl restart yetkisi ver (passwordless sudo for restart only)
cat > /etc/sudoers.d/smartxflow-restart << 'SUDOEOF'
smartxflow ALL=(ALL) NOPASSWD: /bin/systemctl restart smartxflow-web, /bin/systemctl restart smartxflow-scraper, /bin/systemctl restart smartxflow-alarm, /bin/systemctl restart smartxflow-live
SUDOEOF
chmod 440 /etc/sudoers.d/smartxflow-restart

# ── 4. GitHub repo clone ────────────────────────────────────────────────────
echo ""
echo "[4/9] GitHub reposu clonelanıyor..."
if [ -d "$APP_DIR/.git" ]; then
    echo "Repo zaten var, pull yapılıyor..."
    cd "$APP_DIR"
    git pull origin main
else
    git clone "$GITHUB_REPO" "$APP_DIR"
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# ── 5. Python virtualenv + bağımlılıklar ────────────────────────────────────
echo ""
echo "[5/9] Python sanal ortamı ve bağımlılıklar kuruluyor..."
cd "$APP_DIR"
sudo -u "$APP_USER" python3.11 -m venv venv
sudo -u "$APP_USER" venv/bin/pip install --upgrade pip -q
sudo -u "$APP_USER" venv/bin/pip install -r requirements.txt -q
sudo -u "$APP_USER" venv/bin/pip install gunicorn python-dateutil -q
echo "Python bağımlılıkları kuruldu."

# ── 6. .env dosyası ────────────────────────────────────────────────────────
echo ""
echo "[6/9] .env dosyası oluşturuluyor..."
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << 'ENVEOF'
# SmartXFlow — Hetzner Ortam Değişkenleri
# Bu dosyayı gerçek değerlerle doldurun!

SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=YOUR_ANON_KEY_HERE
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY_HERE

SESSION_SECRET=GUCLU_RASTGELE_BIR_SECRET_BURAYA

PAYMENT_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
PAYMENT_CHAT_ID=YOUR_TELEGRAM_CHAT_ID
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID

APIFOOTBALL_KEY=YOUR_APIFOOTBALL_KEY

BETWATCH_COOKIE=YOUR_BETWATCH_COOKIE

excapper_cookie=YOUR_EXCAPPER_COOKIE

REPL_DEPLOYMENT=1
ENVEOF
    chown "$APP_USER":"$APP_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo ""
    echo "⚠️  .env DOSYASI OLUŞTURULDU AMA BOŞ ŞABLON!"
    echo "   Lütfen şu komutu çalıştırın:"
    echo "   nano $APP_DIR/.env"
    echo "   ve tüm değerleri doldurun, sonra devam edin."
    echo ""
    read -p "   .env'i düzenlendi mi? Devam etmek için Enter'a bas..." _
else
    echo ".env zaten mevcut, atlanıyor."
fi

# ── 7. systemd servisleri ──────────────────────────────────────────────────
echo ""
echo "[7/9] systemd servisleri oluşturuluyor..."

# 7a. Web (gunicorn)
cat > /etc/systemd/system/smartxflow-web.service << SVCEOF
[Unit]
Description=SmartXFlow Web (Gunicorn)
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn app:app \
    --workers 2 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile $APP_DIR/logs/gunicorn-access.log \
    --error-logfile $APP_DIR/logs/gunicorn-error.log \
    --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

# 7b. Scraper Engine
cat > /etc/systemd/system/smartxflow-scraper.service << SVCEOF
[Unit]
Description=SmartXFlow Scheduled Scraper
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python scheduled_scraper.py
Restart=always
RestartSec=30
StandardOutput=append:$APP_DIR/logs/scraper.log
StandardError=append:$APP_DIR/logs/scraper.log

[Install]
WantedBy=multi-user.target
SVCEOF

# 7c. Alarm Engine
cat > /etc/systemd/system/smartxflow-alarm.service << SVCEOF
[Unit]
Description=SmartXFlow Alarm Engine
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python alarm_engine.py
Restart=always
RestartSec=30
StandardOutput=append:$APP_DIR/logs/alarm.log
StandardError=append:$APP_DIR/logs/alarm.log

[Install]
WantedBy=multi-user.target
SVCEOF

# 7d. Live Scraper
cat > /etc/systemd/system/smartxflow-live.service << SVCEOF
[Unit]
Description=SmartXFlow Live Scraper
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python live_scraper.py
Restart=always
RestartSec=30
StandardOutput=append:$APP_DIR/logs/live.log
StandardError=append:$APP_DIR/logs/live.log

[Install]
WantedBy=multi-user.target
SVCEOF

# Log klasörü
mkdir -p "$APP_DIR/logs"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR/logs"

systemctl daemon-reload
systemctl enable smartxflow-web smartxflow-scraper smartxflow-alarm smartxflow-live
echo "systemd servisleri oluşturuldu ve etkinleştirildi."

# ── 8. Nginx konfigürasyonu ─────────────────────────────────────────────────
echo ""
echo "[8/9] Nginx ayarlanıyor..."
cat > /etc/nginx/sites-available/smartxflow << NGXEOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    # Letsencrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
        proxy_connect_timeout 120;
        client_max_body_size 10m;
    }
}
NGXEOF

ln -sf /etc/nginx/sites-available/smartxflow /etc/nginx/sites-enabled/smartxflow
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
echo "Nginx ayarlandı."

# ── 9. Servisleri başlat ────────────────────────────────────────────────────
echo ""
echo "[9/9] Servisler başlatılıyor..."
systemctl start smartxflow-web
systemctl start smartxflow-scraper
systemctl start smartxflow-alarm
systemctl start smartxflow-live

sleep 3
echo ""
echo "============================================"
echo " Servis Durumları:"
echo "============================================"
systemctl is-active smartxflow-web     && echo "  ✓ smartxflow-web     ÇALIŞIYOR" || echo "  ✗ smartxflow-web     DURDU"
systemctl is-active smartxflow-scraper && echo "  ✓ smartxflow-scraper  ÇALIŞIYOR" || echo "  ✗ smartxflow-scraper  DURDU"
systemctl is-active smartxflow-alarm   && echo "  ✓ smartxflow-alarm    ÇALIŞIYOR" || echo "  ✗ smartxflow-alarm    DURDU"
systemctl is-active smartxflow-live    && echo "  ✓ smartxflow-live     ÇALIŞIYOR" || echo "  ✗ smartxflow-live     DURDU"

echo ""
echo "============================================"
echo " SSL Sertifikası"
echo "============================================"
echo " DNS A kaydını 91.99.6.245'e yönlendirdikten sonra:"
echo " sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo ""
echo "============================================"
echo " GitHub Actions Secrets (repo'ya ekle):"
echo "============================================"
echo "  HETZNER_HOST = 91.99.6.245"
echo "  HETZNER_USER = smartxflow"
echo "  HETZNER_SSH_KEY = (aşağıdaki private key)"
echo ""
echo " SSH key oluşturmak için:"
echo " ssh-keygen -t ed25519 -C 'github-actions@smartxflow' -f /tmp/deploy_key -N ''"
echo " cat /tmp/deploy_key        # → HETZNER_SSH_KEY secrets'a yapıştır"
echo " cat /tmp/deploy_key.pub >> $APP_DIR/.ssh/authorized_keys"
echo ""
echo "============================================"
echo " KURULUM TAMAMLANDI!"
echo " Web: http://$DOMAIN (SSL sonrası https://)"
echo " Log: journalctl -u smartxflow-web -f"
echo "============================================"
