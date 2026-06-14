# SmartXFlow — Hetzner Kurulum Kılavuzu

## Sunucu Bilgileri
- **IP:** 91.99.6.245
- **OS:** Ubuntu 22.04
- **Model:** CPX22 (2 vCPU, 4GB RAM, 80GB SSD)
- **Domain:** smartxflow.com

---

## ADIM 1 — Sunucuya SSH ile bağlan

```bash
ssh root@91.99.6.245
# Şifre: Hetzner emailindeki şifre (ilk giriş)
```

---

## ADIM 2 — Kurulum scriptini çalıştır

```bash
# Önce repoyu geçici olarak çek
git clone https://github.com/hazardyk27-sudo/SmartXFlow.git /tmp/sxf-setup

# Setup scriptini çalıştır
bash /tmp/sxf-setup/deploy/setup_hetzner.sh
```

Script şunları otomatik yapar:
- Sistem güncellemesi
- UFW firewall (22/80/443)
- `smartxflow` kullanıcısı
- Python 3.11 + virtualenv + tüm bağımlılıklar
- GitHub reposu → `/opt/smartxflow`
- 4 adet systemd servisi
- Nginx HTTP konfigürasyonu

Script `.env` dosyası oluşturur ve durur. **Değerleri gir:**

```bash
nano /opt/smartxflow/.env
```

Gerekli değerler:
| Key | Açıklama |
|-----|----------|
| `SUPABASE_URL` | Supabase proje URL'i |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `SESSION_SECRET` | Rastgele güçlü string (en az 32 karakter) |
| `PAYMENT_BOT_TOKEN` | Telegram bot token |
| `PAYMENT_CHAT_ID` | Telegram chat ID |
| `APIFOOTBALL_KEY` | API-Football key |
| `BETWATCH_COOKIE` | Betwatch.fr cookie |
| `excapper_cookie` | Excapper.com cookie |

`.env` doldurulduktan sonra servisleri başlat:

```bash
sudo systemctl start smartxflow-web smartxflow-scraper smartxflow-alarm smartxflow-live

# Durum kontrol:
sudo systemctl status smartxflow-web
sudo journalctl -u smartxflow-web -f
```

---

## ADIM 3 — DNS Güncelle

Domain yönetim panelinden **A kaydı** ekle:

| Tip | Ad | Değer | TTL |
|-----|----|-------|-----|
| A | @ (veya smartxflow.com) | 91.99.6.245 | 300 |
| A | www | 91.99.6.245 | 300 |

DNS yayılması 1-24 saat sürebilir. Kontrol:

```bash
dig smartxflow.com +short
# → 91.99.6.245 görünmeli

dig www.smartxflow.com +short
# → 91.99.6.245 görünmeli
```

---

## ADIM 4 — HTTPS / SSL Sertifikası (Let's Encrypt)

> **Önkoşul:** DNS A kaydı doğru çözümlenmiş olmalı (Adım 3).

DNS 91.99.6.245'e çözümlenince SSL setup scriptini çalıştır:

```bash
sudo bash /opt/smartxflow/deploy/setup_ssl.sh
```

Script otomatik olarak:
1. DNS kaydının doğru çözümlendiğini doğrular (yanlışsa hata verir)
2. Certbot'u kontrol eder / kurar
3. Nginx HTTP konfigürasyonunu aktif eder
4. `certbot --nginx` ile Let's Encrypt sertifikasını alır
5. Nginx'i HTTP → HTTPS yönlendirme + 443 SSL bloğu ile yeniden yapılandırır

**Başarılı kurulum sonrası:**
- `https://smartxflow.com` → çalışır
- `https://www.smartxflow.com` → çalışır
- `http://smartxflow.com` → otomatik HTTPS yönlendirmesi (301)

**Doğrulama:**
```bash
curl -I http://smartxflow.com
# → HTTP/1.1 301 Moved Permanently
# → Location: https://smartxflow.com/...

curl -I https://smartxflow.com
# → HTTP/2 200

# SSL sertifika detayları:
certbot certificates
```

**Otomatik Yenileme:**
Certbot, Let's Encrypt sertifikasını her 90 günde otomatik yeniler.
Systemd timer aktif olduğunu kontrol et:
```bash
systemctl list-timers | grep certbot
# → certbot.timer görünmeli
```

---

## ADIM 5 — GitHub Actions Auto-Deploy Kurulumu

### 5a. Sunucuda SSH key çifti oluştur

```bash
# Sunucuda root olarak çalıştır
ssh-keygen -t ed25519 -C "github-actions@smartxflow" -f /tmp/deploy_key -N ""

# Public key'i smartxflow kullanıcısının authorized_keys'ine ekle
mkdir -p /opt/smartxflow/.ssh
cat /tmp/deploy_key.pub >> /opt/smartxflow/.ssh/authorized_keys
chown -R smartxflow:smartxflow /opt/smartxflow/.ssh
chmod 700 /opt/smartxflow/.ssh
chmod 600 /opt/smartxflow/.ssh/authorized_keys

# Private key'i kopyala (GitHub Secrets'a yapıştıracaksın)
cat /tmp/deploy_key
```

### 5b. GitHub Secrets ekle

GitHub → repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret Adı | Değer |
|------------|-------|
| `HETZNER_HOST` | `91.99.6.245` |
| `HETZNER_USER` | `smartxflow` |
| `HETZNER_SSH_KEY` | `/tmp/deploy_key` içeriği (-----BEGIN... dahil) |

### 5c. Test Et

```bash
# Replit'ten push yap:
git push --force

# GitHub Actions sekmesini aç → deploy job'u izle
# Hetzner'da:
sudo journalctl -u smartxflow-web -f
```

---

## Nginx Konfigürasyonu

SSL kurulduktan sonra aktif Nginx yapısı (`/etc/nginx/sites-available/smartxflow`):

```
HTTP :80  →  301 HTTPS yönlendirme  (Let's Encrypt challenge hariç)
HTTPS :443 → Gunicorn :8000 proxy
```

Referans dosya: `deploy/nginx-smartxflow.conf`

Nginx'i manuel test/yeniden yüklemek için:
```bash
nginx -t                  # Konfigürasyon test
systemctl reload nginx    # Sıfırsız yeniden yükleme
```

---

## Log Komutları

```bash
# Web (gunicorn)
journalctl -u smartxflow-web -f

# Scraper
tail -f /opt/smartxflow/logs/scraper.log

# Alarm Engine
tail -f /opt/smartxflow/logs/alarm.log

# Live Scraper
tail -f /opt/smartxflow/logs/live.log

# Nginx erişim / hata
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

## Servis Yönetimi

```bash
# Tüm servisleri yeniden başlat
sudo systemctl restart smartxflow-web smartxflow-scraper smartxflow-alarm smartxflow-live

# Tek servis
sudo systemctl restart smartxflow-web

# Durum
sudo systemctl status smartxflow-web
```
