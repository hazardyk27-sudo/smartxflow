---
name: Deployment architecture
description: Hangi servis nerede çalışıyor ve Replit Deployment run komutu
---

## Mimari
| Servis | Sunucu |
|---|---|
| Web app (app.py) | Replit Deployment → smartxflow.com (GCP IP: 34.111.179.208) |
| Scraper Engine + Alarm + Sinyal + Live Scraper | Hetzner VPS (91.99.6.245) — systemd servisleri |
| Replit workspace workflows | Sadece geliştirme için; Hetzner scraperlar çalışırken workspace workflow'larına gerek yok |

## Replit Deployment Run Komutu
Doğru: `REPL_DEPLOYMENT=1 python app.py` (CLIENT mode, scraper yok)
Yanlış (eski): `python app.py & bash run_services.sh & wait` (scraper da başlatıyordu → çift scraping)

**Why:** Hem Hetzner hem Replit Deployment aynı anda scraper çalıştırınca Supabase statement timeout (57014) hatası oluşuyordu. Fix: 2026-06-20.

## Hetzner Systemd Servisleri
- smartxflow-web.service (gunicorn port 5000)
- smartxflow-scraper.service
- smartxflow-alarm.service  
- smartxflow-live.service
- nginx (reverse proxy, 80→5000)

## alarm_engine Bellek Sorunu
alarm_engine.py Hetzner'de ~1.7GB RAM kullanıyor (Jun19'dan beri çalışıyor). alarm_calculator.py'nin _telegram_sent_cache ve _matches_cache'inde TTL/temizleme mekanizması yok — zamanla büyüyebilir.
