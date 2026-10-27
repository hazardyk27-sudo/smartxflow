# Admin → GitHub PRATİK ARŞİVİ

## Günlük çalışma

CAPİTALE deposundaki `.github/workflows/sxf-admin-archive.yml` her gün **23:00 UTC / 02:00 Europe/Istanbul** saatinde çalışır. Türkiye takvimine göre önceki tamamlanmış günü ve geriye dönük üç günü kontrol eder; eksik tarihleri arşivler, doğrulanmış tarihleri checksum ile kontrol edip değiştirmeden bırakır. Böylece kısa süreli başarısızlıklar, kaynak satırları saklama temizliğiyle silinmeden tekrar denenebilir. Plan, SmartXFlow'un **02:17 UTC** saklama temizliğinden önce çalışır. Actions kuyruğu veya kaynak hatası işi geciktirirse bu zamanlama tek başına silme işlemini durdurmaz; GitHub Actions geçmişindeki başarısız çalışma incelenip admin ekranından eksik tarih tekrar başlatılmalıdır.

İş akışı kaynak kayıtları salt okunur alır, PRATİK formatındaki üç dosyayı üretir, geri açıp SHA-256/çizelge/gelecek gözlem kontrollerini yapar ve yalnızca doğrulamadan sonra üç günlük dosyayı ve `archive/pratik_arsiv/index.json` gün özetini CAPİTALE deposunun `main` dalına tek commit olarak yazar. GitHub deposuna yazma izni Actions'ın kendi `GITHUB_TOKEN`'ına verilir.

Admin sayfası: `/admin/sxf-archive`. Yönetici oturumundan son dört gün içindeki tamamlanmış bir gün seçilip aynı Actions işi elle başlatılabilir. İş geçmişi GitHub Actions'tan okunur. Ayrıca “Arşivlenen günler” listesi, CAPİTALE deposundaki `archive/pratik_arsiv/index.json` dosyasından en yeni tamamlanmış günden eskiye sıralı olarak beslenir. Her satır gün, fixture ve alarm sayısı ile sıkıştırılmış boyutu gösterir. İndekste olmayan tarihler “Eksik”; checksum veya sayaç doğrulaması bulunmayan kayıtlar “Kontrol gerekli”; kaynak arşiv durumu PARTIAL olan doğrulanmış kayıtlar “Arşivlendi · kaynak kısmi” olarak görünür. Diğer doğrulanmış kayıtlar “Arşivlendi” olur. İndeks halka açık depodan salt okunur alınır; admin tokenına ek GitHub kapsamı verilmez. Kuyruğa alınma, arşivin başarıyla kaydedildiği anlamına gelmez.

## Saklanan veri ve konum

Günlük dosyalar mevcut PRATİK arşivinin yerleşimini kullanır:

`archive/YYYY/MM/DD/05_pratik_arsiv/`

- `checkpoints.jsonl.gz`: 34 T noktası; 1X2, OU2.5 ve BTTS için kaynak oran, yüzde, GBP miktarı, hacim ve gerçek gözlem zamanı.
- `alarms.jsonl.gz`: Maçla eşleşen alarm satırları ve kaynak tablo adı.
- `manifest.json`: Gün, fixture/sonuç/alarm sayıları, kapsama, dosya boyutları ve açılmış JSONL verisi üzerinde SHA-256.

Kaynaklar `public.fixtures`, `public.live_fixtures`, üç `moneyway_*_history` tablosu ve mevcut alarm tablolarıdır. Kaynak tablolara yazılmaz veya silme yapılmaz. Günlük arşiv `SXF_arastirma_arsivi/` ve Learning Archive'den ayrıdır; bu dizinleri değiştirmez.

## Tekrarlama ve hata kuralları

- Hedefte daha önce kaydedilmiş tam arşiv varsa manifest, fixture/alarm kayıt sayısı, 34 nokta çizelgesi, checksum ve gelecekteki gözlem yasağı yeniden denetlenir. Hepsi geçerse mevcut gün olduğu gibi bırakılır.
- Üç dosyadan biri eksikse, manifest kimliği uyuşmuyorsa veya doğrulama başarısızsa işlem durur; eski dosyaların üzerine yazılmaz.
- Kaynakta fixture bulunmazsa veya bağlantı/veri doğrulaması başarısızsa Action başarısız olur; gün tamamlandı sayılmaz.
- Kısmi bir klasör otomatik silinmez veya onarılmaz. Önce GitHub Action çıktısı ve kaynak günü incelenir.

## Özel ayarlar

### CAPİTALE GitHub Actions sırrı

`PRATIK_ARCHIVE_DATABASE_URL`: `public.fixtures`, `public.live_fixtures`, üç piyasa tarihçe tablosu ve kullanılan alarm tablolarında yalnız SELECT yetkili PostgreSQL rolünün SSL bağlantısı. Supabase service-role veya yazma yetkili `postgres` bağlantısı kullanmayın. Sır GitHub → Settings → Secrets and variables → Actions üzerinden özel olarak eklenir.

### SmartXFlow yönetici sunucusu

Mevcut `CAPITALE_GITHUB_ACTIONS_TOKEN`, yalnız `hazardyk27-sudo/capitale` deposunun Actions iş akışını tetikleme ve çalışma durumunu okuma iznine sahip olmalıdır. Veritabanı DSN'i SmartXFlow'a ya da tarayıcıya verilmez. Token veya DSN koda, rapora ya da loglara yazılmaz.

Kod değişikliği önce gözden geçirme PR'ında tutulur. Bu belge üretime aktarım veya PR birleştirme onayı değildir.
