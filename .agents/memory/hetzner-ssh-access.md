---
name: Hetzner SSH Access
description: SSH erişim bilgileri ve Hetzner'de yapılabilecek işlemler
---

# Hetzner SSH Access

## Bağlantı
- **Secret**: `HETZNER_IP` (IP adresi) + `HETZNER_PASSWORD` (root şifresi)
- **Komut**: `sshpass -p "$HETZNER_PASSWORD" ssh -o StrictHostKeyChecking=no root@$HETZNER_IP`
- **Repo yolu**: `/root/smartxflow`

## Yapılabilecekler
- `git pull` — GitHub'dan son kodu çek
- `git stash && git pull && git stash pop` — local değişiklik varsa stash ile koru
- Servis restart: `systemctl restart smartxflow-sinyal` (veya ilgili servis adı)
- Scraper manuel tetik: `python3 polymarket_scraper.py --backfill`

**Why:** Replit'ten Hetzner'e SSH bağlantısı mümkün; pull/restart işlemleri için kullanıcının terminale geçmesine gerek yok.
