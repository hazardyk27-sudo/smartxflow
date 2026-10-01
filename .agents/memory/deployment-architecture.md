---
name: Deployment architecture
description: Hangi servis nerede çalışıyor ve Replit Deployment run komutu
---

## Doğrulanan web kurulumları (2026-10-01)
- Hetzner web servisi: `/opt/smartxflow`, `smartxflow-web.service`, Gunicorn `127.0.0.1:8000`; Nginx'in HTTP/80 bloğu bu porta proxy yapıyor.
- Ayrı scraper kod ağacı: `/root/smartxflow`; web dağıtımı için bu dizini güncelleme veya servislerini yeniden başlatma.
- Aynı tarihli Replit deployment metadata'sı da `smartxflow.com` alan adını Replit VM yayınına bağlı gösteriyordu. Public DNS Hetzner sunucusuna çözülmüyor ve alan adı eski JS'i sunuyordu.
- Replit workspace workflow'ları geliştirme/test içindir; Hetzner web servisine otomatik olarak yansımaz.

**Why:** Aynı ürünün Hetzner'de çalışan web servisi ve alan adına bağlı ayrı bir Replit yayını vardı; birini güncellemek diğerinin public trafiğini güncellemiyor.

**How to apply:** Web kodu yayınlarken hedefi kullanıcı isteğine göre belirle, önce çalışan servisin dizinini doğrula. Hetzner-only isteğinde `/opt/smartxflow` ve `smartxflow-web.service` ile sınırlı kal; DNS'i değiştirme veya Replit'i yayınlama. Public-site hedefi istenirse, canlı alan adı içeriğini ayrıca doğrula.

## alarm_engine Bellek Sorunu
alarm_engine.py Hetzner'de ~1.7GB RAM kullanıyor (Jun19'dan beri çalışıyor). alarm_calculator.py'nin _telegram_sent_cache ve _matches_cache'inde TTL/temizleme mekanizması yok — zamanla büyüyebilir.
