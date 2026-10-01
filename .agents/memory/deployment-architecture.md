---
name: Deployment architecture
description: Hetzner canonical kaynak, Replit geliştirme/Preview ve aynı frozen snapshot'ın iki production hedefinde yayınlanması için release standardı.
---

## Kalıcı kaynak ve release standardı

- Hetzner canonical ana kaynaktır. Replit workspace geliştirme alanı, Replit Preview kullanıcı onay alanı ve Replit production web runner'dır.
- Her geliştirme, en son onaylanmış Hetzner canonical snapshot'ının Replit workspace'e senkronizasyonuyla başlar. Sync tamamlanmadan geliştirmeye başlama.
- Kod ve dokümantasyon değişiklikleri yalnızca Replit workspace'te yapılır. Hetzner production/current üzerinde elle düzenleme yapma; Hetzner ve Replit'te paralel düzenleme yapma.
- Kullanıcı Replit Preview'da açıkça onaylamadan Hetzner canonical'ı değiştirme veya release aktarma.
- Preview onayından sonra Replit workspace'in tam release içeriğini değiştirilmez frozen snapshot olarak sabitle. Benzersiz `RELEASE_ID` ata; aynı snapshot için tracked file count ve deterministik full-tree SHA256 fingerprint'i bir release manifestine kaydet.
- Count ve fingerprint aynı açık tracked-file manifestini kullanır: `.git` hariç, her release dosyası için normalize POSIX göreli yol, dosya türü/modu ve tam bayt içeriğinin SHA256'sı (symlink için hedef) kaydedilir; girdiler göreli yolun UTF-8 bayt sırasına göre sıralanıp belirsizliğe izin vermeyen sabit formatta serileştirilir ve manifestin SHA256'sı alınır. Release dışında bırakılan generated/runtime dosyaları açıkça listelenir. Snapshot dondurulduktan sonra dosya ekleme, silme veya düzenleme yapılmaz.
- Aynı frozen snapshot'ı SSH/rsync ile Hetzner incoming/release alanına aktar ve orada test et. Ardından aynı snapshot'ı Replit production web runner'a publish et; hedeflerden birine farklı bir çalışma ağacı deploy etme.
- Final doğrulamasında Replit ve Hetzner için `RELEASE_ID`, tracked file count ve fingerprint'i karşılaştır. Üç değer de birebir eşleşmeden deploy tamamlanmış sayılmaz.
- Yeni deploy öncesi Hetzner ve Replit ağaçlarında divergence varsa önce karşılaştır ve farkları çöz; mevcut canonical veya frozen release'i körlemesine üzerine yazma.
- GitHub bu zorunlu deployment yolunun parçası değildir.

**Why:** Hetzner ve Replit ayrı çalışma ve yayın hedefleridir. Preview onayı, immutable snapshot ve üçlü release kimliği eşleşmesi olmadan iki tarafta farklı kod çalışabilir; production/current üzerinde elle değişiklik de karşılaştırılmamış divergence yaratır.

**How to apply:** Her değişiklikte sırayı koru: onaylı Hetzner snapshot'ını Replit'e sync et → yalnız Replit'te düzenle → Preview onayı al → `RELEASE_ID` ile snapshot'ı dondur ve count/fingerprint üret → aynı snapshot'ı Hetzner'e aktar/test et ve Replit production'a publish et → iki hedefin üç release değerini karşılaştır. Herhangi bir uyuşmazlıkta tamamlandı deme; önce divergence'ı çöz.

## Hetzner dizin ayrımı
- Hetzner web repo'su `/opt/smartxflow`; ayrı scraper repo'su `/root/smartxflow`. Web release'inde scraper repo'sunu veya servislerini değiştirme.

## alarm_engine Bellek Sorunu
alarm_engine.py Hetzner'de ~1.7GB RAM kullanıyor (Jun19'dan beri çalışıyor). alarm_calculator.py'nin _telegram_sent_cache ve _matches_cache'inde TTL/temizleme mekanizması yok — zamanla büyüyebilir.
