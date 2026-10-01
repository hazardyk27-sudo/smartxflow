---
name: Hetzner SSH Access
description: SSH erişim bilgileri ve Hetzner'de yapılabilecek işlemler
---

# Hetzner SSH Access

## Bağlantı
- **Secret**: `HETZNER_IP` (IP adresi) + `HETZNER_PASSWORD` (root şifresi)
- **Komut**: `sshpass -p "$HETZNER_PASSWORD" ssh -o StrictHostKeyChecking=accept-new root@$HETZNER_IP`
- **Web repo yolu**: `/opt/smartxflow` — aktif web uygulaması `smartxflow-web.service` tarafından çalıştırılır.
- **Scraper repo yolu**: `/root/smartxflow` — web uygulamasından ayrı bir kod ağacı; web-only dağıtımda dokunma.

## Yapılabilecekler
- Hedef repo ve `git status` doğrulandıktan sonra yalnız ilgili servisin kodunu güncelle.
- Web dağıtımında yalnız `systemctl restart smartxflow-web.service` kullan; scraper servislerini yeniden başlatma.
- Scraper manuel tetik: `python3 polymarket_scraper.py --backfill`

**Why:** Hetzner'de web ve scraper kodları ayrı dizinlerde; `/root/smartxflow` içinde dağıtımla ilgisiz yerel scraper değişiklikleri bulunabilir.

**How to apply:** SSH ile bağlandıktan sonra systemd `WorkingDirectory` ve repo durumunu salt okunur biçimde kontrol et. Yerel değişiklikleri koru; web güncellemesinde sadece `/opt/smartxflow` ile web servisini değiştir.
