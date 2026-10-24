# SMARTXFLOW — TAM SOHBET, KARAR, UYGULAMA VE CANLI DURUM DEVRİ
## 24 Ekim 2026 — Yeni sohbet için ana dosya

> **Kapsam ve dürüstlük notu:** Bu dosya, mevcut konuşmada doğrulanabilen araç kayıtlarını, proje geçmişinden aktarılan kararları ve ulaşılabilen önceki sohbet özetlerini tek yerde birleştirir. Bütün eski sohbetlerin kelimesi kelimesine arşivi değildir; görünmeyen mesajlar varmış gibi uydurulmamıştır. Devam edecek asistan bu belgedeki **doğrulanmış**, **tarihsel bildirim** ve **bekleyen** ayrımını korumalıdır.

# 1. Yeni sohbetin ilk talimatı

Yalnızca **SmartXFlow** projesinde çalış. Canonical repository: **hazardyk27-sudo/smartxflow**.

**Şu anki en kritik görev:** Hetzner'deki ana **Sinyal Motoru / Base worker** güvenlik nedeniyle duruyor. Bağımsız 80 saatlik maç keşif servisi çalışır duruma getirildi ve bütün gelecek maçları kuyruğa yazabiliyor, ancak ana worker işlerini bitirmiyor. Sorunun kaynağını güvenli biçimde belirleyip worker'ın sürekli, doğrulanmış şekilde çalışmasını sağlamak gerekiyor.

Kullanıcının kesin koşulları:
- **Maç, veritabanı verisi, geçmiş snapshot, sinyal kaydı veya kuyruk kaydı SİLİNMEYECEK.**
- Tek güncel sinyal motoru olacak. Uygulamada “Güncel V3 / Eski V2 arşivi” biçiminde çift motor görünümü olmayacak.
- Beş eski sinyal kategorisi olan **Underdog, Confirmed, Fake Sharp, Early Money Lock** ve aynı eski motor ailesinin kullanım dışı akışları tekrar devreye alınmayacak. Eski dedicated **smartxflow-sinyal.service** kapalı/disabled kalacak; ana güncel sistem onun aktif olmasına bağımlı olmayacak.
- Sinyal motoru 7/24 **agentsiz ve insan beklemeden** çalışacak.
- İlk öncelik mevcut **geçerli iş kuyruğu**, sonra **gelecek tarihli maçların kronolojik ve güncel gün öncelikli** taranması; geçmiş maçlar otomatik olarak tekrar işlenmeye zorlanmayacak. Tarihsel kuyruk/veri **silinmeyecek**.
- Eksik veri varsa o maç için güvenli skip; bütün motoru takılı bırakma. Eksik snapshot t-72, t-6 gibi checkpoint'lerde **istenen saate en yakın gerçek ve geçerli gözlem** kullanılacak; kaynak zamanı/hakikat uydurulmayacak.
- **Replit'e dokunma**: kullanıcının bu işlerde tekrarladığı açık “Replit hariç” sınırı. Yeni bir yayın için bunun devam edip etmediğini netleştir.
- **Kullanıcının kişisel bilgisayarına hiçbir şekilde erişme**; masaüstü kontrolü açıkça yasaklandı.
- Force-push, reset, rebase, cherry-pick, zorla Git history yazımı yok. Çalışma dalları normal merge ve fast-forward ile senkronlanmalı.
- Kullanıcıya adıyla hitap etme (özellikle önceki isim kullanımından rahatsız olduğunu belirtti).
- “Test geçti” ile “servis canlı ve çalışıyor” birbirine karıştırılmayacak; iddialar kanıtlı olmalı.

# 2. Repo, ortam ve release sözleşmesi

**GitHub:** https://github.com/hazardyk27-sudo/smartxflow

- **preview:** geliştirme/test, aktif DEVELOPMENT/PREDICTOR rol talimatları burada.
- **main:** production için onaylanmış SHA.
- **Hetzner:** production web ve servisler; GitHub Actions SHA'ya kilitli deploy.
- **Replit:** yalnız preview; bu devirde **erişilmedi, senkronlanmadı**.
- **Supabase:** paylaşılan üretim verisi. Proje kimliği: **pswdvnmqjjnjodwzkmkp**. Sırlar, bağlantı anahtarları veya .env içerikleri dosyaya yazılmadı.
- **GitHub canonical:** Sunucuda canlı dosyaları doğrudan el ile değiştirme; deploy, main'de onaylı exact SHA'nın salt fast-forward kopyasıdır.

İlgili sözleşmeler:
- main:/AGENTS.md
- preview:/AGENTS.md
- preview:/.agents/contracts/RELEASE_FLOW.md
- preview:/.agents/roles/DEVELOPMENT.md
- preview:/.agents/milestones/DEVELOPMENT.md

RELEASE_FLOW.md temel kuralı: preview üzerinde kod+test; main ile diverge ise **main'deki yeni değişiklikleri koruyarak normal iki ebeveynli PR merge**; ardından main için fast-forward (force:false, beklenen eski SHA ile); GitHub Actions tam main SHA'sını Hetzner'e deploy eder. Replit hariç release, kullanıcı tarafından **her production yayınında ayrı** açıkça onaylanmalıdır. Geçmiş onay sonsuz yayın hakkı değildir.

Önceki konuşmalarda birden çok kere main / preview arasında yeni UI/admin commitleri geldiği için normal PR merge tekrarlandı. Hiçbir yeni main değişikliği atılmamalıdır. Her yeni sohbette HEAD ve karşılaştırma tekrar okunmalı.

## Production servisleri

- smartxflow-web.service — web/API
- smartxflow-scraper.service — ana kaynak tarama
- smartxflow-alarm.service — alarm
- smartxflow-live.service — canlı veri
- smartxflow-poly.service — Poly
- smartxflow-predictor-orchestrator.service — Predictor
- smartxflow-base-worker.service — **tek güncel sinyal hesaplayan/işleyen worker**, 7/24 hedef
- smartxflow-base-guarded-recovery.service ve .timer — güvenlik frenli worker toparlama
- smartxflow-base-fixture-discovery.service — **80 saat ileriye dönük bağımsız fixture keşfi; sinyal değerlendirme yapmaz**
- smartxflow-sinyal.service — **eski motor; kapalı/disabled kalmalı**
- smartxflow-learning-archive-prematch.timer ve postmatch.timer — günlük/sonuç sonrası öğrenme arşivi otomasyonu

Bağımsız keşif ve ana worker iki ayrı bağımsız teknik **görev** yapıyor; kullanıcının istemediği “çift güncel sinyal motoru” anlamına **gelmiyor**. Keşif sinyal üretmez, yalnız gelecekteki maçların gereken kuyruk işlerini oluşturur.

# 3. Güncel sinyal motorunun veri ve checkpoint sözleşmesi

24 Ekim'de SQL ve Python kodunda görülen aktif ruleset:
**SXF_SIGNAL_MOTOR_V3_2026_10_24**

Sinyal motorunun dondurulmuş 11 kontrol işi:
1. T-72: EARLY_CORE
2. T-60: EARLY_CORE
3. T-40: EARLY_CORE
4. T-24: EARLY_CORE
5. T-12: EARLY_T12
6. T-8: BASE
7. T-6: BASE
8. T-6: EARLY_RETENTION
9. T-5: EARLY_RETENTION
10. T-4: EARLY_RETENTION
11. T-3: EARLY_RETENTION

Bu liste **base_signal_engine/scheduler.py** kaynağından, 24 Ekim'de doğrulandı. Retention T-6/T-5/T-4/T-3 noktaları ayrıca veri tutar; yeni Base tetiklemesi ile karıştırılmamalıdır. İş anahtarı fixture UID + güncel kickoff + checkpoint family/hours + ruleset sürümüne dayanır.

İlgili tablolar/kaynaklar:
- public.fixtures — fiziksel fixture_uid ve kickoff_utc
- public.sxf_base_checkpoint_jobs — durable checkpoint iş sırası; PENDING/LEASED/COMPLETED/SUPERSEDED vb.
- public.sxf_base_reconcile_jobs — reconciliation
- public.sxf_base_discovery_cursors — eski durable discovery watermark
- public.sxf_base_fixture_drift_events — değişen kickoff kimliğinin append-only kanıtı
- market para/oran snapshot ve sinyal event tabloları — bunlar tarihsel kayıt olarak korunmalı
- public.sxf_base_health_snapshot() — okuma amaçlı durum özeti

**Dikkat:** Bağımsız 80 saatlik keşif servisi, durable discovery cursor'unun last_scanned_at alanını ilerletmeyebilir. Bu alan eski ana worker'ın tarama cursor'udur; sırf eski kalmasına bakarak bağımsız keşif başarısız denmemeli. Ayrı servis günlüğü + gelecekteki fixture'ların 11/11 kuyruk kapsamı birlikte doğrulanmalı.

## İşletim öncelikleri

- Ana worker güncel V3 için LIVE lane'den future-kickoff job claim yapar.
- Kuyruk önce tüketilir, kalan kapasiteyle gelecekteki fixture discovery yapılır.
- Checkpoint geri dönük tarihli olsa da maç ileride ise gerçek zamanlı ve mevcut snapshot uygunluğu kurallarına uyulmalı.
- Eski kickoff, eski sürüm veya maç başlamış iş kayıtları SQL'de tutulur; koruma/retention mantığı ayrı; silme yok.
- Supabase RPC'lerinde claim/renew/complete/skip operations atomic fencing ve lease token ile çalışmalı; kayıp ACK bir önceki işlemin commit edilmediğini **kanıtlamaz**.
- Hata nedeniyle durdurma doğru olduğunda bunu aşmak yerine nedenini ölç; veri duplikasyonu ve tarihi tekrar yazmayı önle.

# 4. UI, sinyaller ve daha önce raporlanan işlevsel sorunlar

Bu belgede anlatılan son operasyon, arayüzün tam işlevsel denetimi değildir. Aşağıdaki şikâyetler önceki sohbetlerden taşınmıştır:

1. “Güncel V3 / Eski V2 arşivi” sekmeleri kullanıcı tarafından reddedildi. Kullanıcı tek güncel sinyal motoru ve onun düzgün görünmesini istiyor.
2. Her sinyal ailesinin ayrı kartı açılmalı; ilgili kart tıklanınca o sinyale ait maçlar görünmeli. V1, V2, HEAVY vb. **sinyal etiketleri**, geçmiş/yeni ayrı çalışan motor sürümü ile karıştırılmamalı.
3. “Heavy Concentration” sonuç ekranında 23 Ekim karşılaşmalarında kötü, sıkışık masaüstü görünümü; tablo satırlarında durum yazıları üst üste binmiş, “On time + archive” yazıları taşmış, score/lig/zaman alanları kalabalık ve karışık. Tema SmartXFlow ana tasarımıyla desktop/mobile uyumlu olmalı.
4. Stuttgart–Gladbach için HEAVY yanlış işaretleme raporlandı. Bochum–Wolfsburg HEAVY T-6'da doğru, güncel AS_OF anında geçersiz olabileceği saptandı. Tarihi tek anın işareti ile güncel sinyalin geçerliliği ayrı tutulmalı.
5. Kullanıcı “bütün maçların eksiksiz taranması” diye ısrar etti; raporda görünmeyen maçların sebebi kuyruk ve eksik veri mi, UI filtreleme mi, stale signal mı ayrıştırılmalı.
6. Sonuç/maç skoru bazen yanlış ya da boş gösterildi. Seçili dile göre çeviriler bazı alanlarda eksik kaldı; Poly çevirisi o aşamada hariç tutulmuştu.
7. Analizler V4'ün tema uyumu, desktop/mobile responsive tasarım ve doğru skor/sinyal statüsü isteniyordu. Kod uygulanmış olması tüm alanların canlı doğrulandığı anlamına gelmez.

# 5. Diğer SmartXFlow bağlamları — kaybolmaması gerekenler

## Poly

- Sadece futbol markets/trades; futbol dışı maçlar eleme yapılırken doğru maçları da yanlış eleme riski korunarak düzeltilmeli.
- Pozisyon toplamı **en az 1.000 USD** eşik.
- Fill/activity satırı sayısını tek tek işlem saymak yanıltıcı; pozisyon bazlı sayım.
- Hetzner production ana kaynak; Replit preview, GitHub kaynak olarak senkron mekanizması.
- Eskiden lisans yokken matches API 403 görülmüştü; login sonrası 924 maç/2,5 sn örneği raporlandı. Bu eski tanı, güncel üretim kanıtı değil.

## Predictor / analizler / öğrenme arşivi

- Predictor Stage 1 -> Stage 2 -> Stage 3 sırası; Stage 1 kullanıcı kapsamındaki bütün geçerli fixture'ları içeride araştırır, dışarı yalnız dikkat çekici adayları raporlar.
- Görünür her Predictor maçında somut tek preference (market + selection) olmalı; BET/WATCH/PASS action ayrı kavram. PASS olsa bile “tercih yok” yazılmaz.
- Önceki kullanıcı kararı: en güvenilir BET, daha az güvenli WATCH, güvensiz listeden çıkarılır; Predictor'ın formel arşiv kuralı yine ayrı geçerlidir.
- Kendi tahmin günlüğü ile Learning Archive iki ayrı zorunlu ürün. Adayın PRE kaynakları prediction_at kesimine göre dondurulur, POST bilgisi PRE'ye taşınmaz. Archive branch: learning-archive, repo aynı.
- Formal Stage 1 tercihleri ve Stage 3 tercihleri matched case set üzerinde ayrı settlement ve ROI/hit-rate kıyaslaması yapılır.
- Analizci rolünde takım performansı xG/xGA, şut kalitesi, rakip gücü, ev/deplasman ve benzer seviye maçlar üzerinden okunur; ham 5/5 seri tek başına değerli sayılmaz. Kaynaklar WhoScored, SofaScore, Understat, FBref, Flashscore, Opta/StatsBomb, FootyStats.
- Bahis stratejisi için daha önce agresif yükselen oranlara basit hafif filtre önerileri ve 9 Ekim sonrası performans sorguları konuşuldu; bunlar canlı sinyal motorunun kanıtlanmış yeni kuralı olarak **varsayılmamalı**.

## Veritabanı maliyetleri

- Supabase'de yaklaşık **5,46 GB indeks** bilgisi önceki sohbette incelendi.
- Bazı Moneyway ve SXF indeksleri yüzlerce MB düzeyinde; gereksiz indeks tespiti ve daha az storage talebi oldu.
- İndeks silme veya migration uygulanmış olduğuna bu belgeden karar verilmez; snapshot/sinyal verisi silmek kullanıcı tarafından açıkça yasak.

# 6. 20–24 Ekim çalışmaları: neden bu duruma gelindi?

Bu bölümde kullanıcı talepleri ve operasyonel olaylar zaman sırasındadır. “İş yapıldı”, “CI geçti”, “servis çalıştı” ve “kalıcı üretim doğrulandı” farklı şeylerdir.

## 20–21 Ekim: eski motoru kaldırma, backlog, 7/24 çalışma

- Kullanıcı önce eski Underdog/Confirmed/Fake Sharp/Early Money Lock motorlarını kaldırma; tek **Sinyal Motoru** adı; en yakın gerçek T-hour snapshot; eksik veri için o maçı atlama ve taramayı durdurmama şartlarını verdi.
- Motorun tüm geçmiş/gelecek maçları aynı anda tarayıp tıkanmaması, önce içinde bulunulan gün, sonra ilerideki günlere sırayla geçmesi istendi.
- Eksik ve geciken HEAVY dahil sinyaller şikâyet edildi; bazı gün 5+ HEAVY beklenirken eksik gösterim, görünen 10/15 sinyal farkı tartışıldı.
- Ana worker ilk etapta 24 saatlik kontrollü modda olduğundan insan müdahalesi olmaksızın kalıcı, otomatik 7/24 sürdürme istendi.
- “Maç veya veri silmek” çözüm olarak açıkça reddedildi. Başlamış maçların eski kayıtlarının kalması veri kaybı sebebi olmamalı; **aktif tarama gelecekteki maçlara odaklanmalı**.
- Kullanıcı “Eski V2 arşivi / Güncel V3” çift sekmesini de reddetti, hatalı eski servisin kapalı, doğru tek güncel motorun çalışır olmasını istedi.

## 22–23 Ekim: HEAD ayrışması, normal merge, güvenli yayına alma

- Production `main` ve geliştirme `preview` arasında ilave üretim değişiklikleri olduğu için tek taraflı üstüne yazma yapılmadı.
- PR **#64** ile main'in yeni içerikleri preview'e normal merge edildi; kaynak ve sürüm akışları senkronlandı. Önceki ortak production/preview SHA: `26e03a48df34eb1534b34cd5e9f652b66e7e56f5`.
- Deploy ve ilgili testler başarıyla koşturuldu; ancak **bağımsız fixture discovery aktivasyonu başarısız kaldı**, çünkü workflow hâlâ emekliye ayrılmış `smartxflow-sinyal.service` için `active` bekliyordu. Somut hata: `DISCOVERY_STOP: dependency_down=smartxflow-sinyal`.
- Böylece “yayın başarılı ama sinyal motoru tamamen çalışmıyor” durumunun nedenlerinden biri saptandı: eski motoru kapatma kararı ile workflow bağımlılığı çatışıyordu.
- Main'e yeni üretim admin/archive UI commitleri geldikçe kaybetmemek için PR **#65**, sonra PR **#66** ile normal iki ebeveynli merge tekrarlandı.
- Bu revizyonlarda hiç force push/reset/rebase/cherry-pick uygulanmadı.

## 24 Ekim: legacy check düzeltmeleri, CI ve aktivasyon

Üretim kodunda yapılan somut düzenlemeler:

1. `.github/workflows/base-fixture-discovery-hetzner-enable.yml`: Eski `smartxflow-sinyal` servisini **aktif olması gereken servis listesi** dışına aldı; tersine inactive/disabled olmasını doğrulayan kontrol eklendi. Bağımsız keşif aktivasyonu modern mimariyle uyumlu hâle geldi.
2. `.github/workflows/base-autonomous-hetzner-enable.yml`: Ana worker aktivasyon dependency kontrolünde aynı legacy ayrımı yapıldı; eski servis kapalı kalmalı. **Önemli: bu workflow manuel `workflow_dispatch` korumalıdır**. Test preflight'ı bunu şart koştuğundan denenen `push` tetiklemesi geri alındı. Ana worker için bu manuel aktivasyonun başarıyla yapıldığı iddia **edilemez**.
3. `tests/test_base_activation_legacy_retirement_contract.py`: Legacy kapalıyken güncel discovery/worker aktivasyon koşulları için regresyon testi.
4. `.github/workflows/base-autonomous-recovery-checks-20261021.yml` ve `.github/workflows/signal-motor-part3-preflight-20261021.yml`: Yeni test ve activation-contract kontrolleri eklendi.
5. `base_signal_engine/fixture_discovery_worker.py`: Fixture horizon doğrulama hatalarında güvenli ve açık reason codes: `CURSOR_UNINITIALIZED`, `UNIVERSE_CAP`, `CHECKPOINT_RULE_DUPLICATE`, `COVERAGE_INCOMPLETE`; hassas değerleri loglamadan teşhis.
6. `.github/workflows/base-worker-hetzner-diagnostic-20261021.yml`: Korumalı, salt-okunur Hetzner tanı iş akışında worker, guard ve discovery durumlarının daha görünür olması.
7. Kaynak/preflight gate önce, worker workflow'una yanlışlıkla otomatik push tetikleyicisi eklendiği için başarısız oldu; bu yanlış düzenleme kaldırıldı ve gate sonra başarılı oldu. GitHub report yayın adımının 409 concurrent bot commit hatası da sonraki çalıştırmada düzeldi.

CI/doğrulama:
- Base motor testleri: **294 test geçti** (~1,90 sn). İlk rapor yayınlama 409 yarış hatasına rağmen sonraki CI run **40054511930 SUCCESS**.
- Kaynak preflight: **264 test geçti**, düzeltilmiş run **40054556381 SUCCESS**.
- GitHub production deploy: **run 40054698927, job 120754976173 SUCCESS**, `DEPLOY_OK SHA=d96c0045781f6e66c7a6efed03ff1c5b6971796c`, `UNIT_SYNC_OK`; web/scraper/alarm vb. ilgili servis ve archive prematch/postmatch timer kontrolü olumlu.
- Windows EXE run **40054698926 SUCCESS** ve Standalone Scraper run **40054698928 SUCCESS**.
- Predictor deploy run **40054741890 SUCCESS**.
- Bağımsız discovery aktivasyonu: **run 40054698943, job 120754975127 SUCCESS**; `BASE_DISCOVERY_ACTIVATED_SHA=d96c...`, `BASE_DISCOVERY_FINAL_ACTIVE=active`, `BASE_DISCOVERY_FINAL_ENABLED=enabled`, `BASE_DISCOVERY_FINAL_SHA=d96c...`, `BASE_DISCOVERY_80H_OK`. Bu, **keşif servisi** içindir; ana worker'a eşit değildir.

## Tam olarak hangi commit yayınlandı?

24 Ekim saat yaklaşık 02:43 UTC son okumasında:
- `main` SHA: **d96c0045781f6e66c7a6efed03ff1c5b6971796c**
- `preview` SHA: **d96c0045781f6e66c7a6efed03ff1c5b6971796c**
- Hetzner deploy doğrulama: aynı **d96c…** SHA, başarılı.

**Bu devir dosyasının dokümantasyon commit'i** daha sonra `preview` üzerine yazılacağı için preview HEAD artık belge commit'i kadar ileride olabilir; bu, kodun production'dan ayrıştığı anlamına tek başına gelmez. Yeni sohbette git HEAD'leri taze oku. Dökümantasyon commit'ini production'a otomatik alıp deploy etme.

# 7. CANLI KANIT — 24 Ekim 2026 / kontrol anı

Aşağıdaki değerler doğrudan 24 Ekim **02:43:44–02:43:50 UTC** (İstanbul **05:43**) Supabase read-only sorgularıyla ölçüldü. Anlık görüntüdür; sonraki saatler için tahmin veya garanti değildir.

## 7.1 Ana kuyruk sağlık özeti

`select public.sxf_base_health_snapshot();` dönüşü:

| Alan | Değer | Yorum |
| --- | ---: | --- |
| ruleset | `SXF_SIGNAL_MOTOR_V3_2026_10_24` | Güncel ruleset |
| checkpoint_queue.total | 9.493 | Toplam kalıcı iş |
| checkpoint_queue.completed | **301** | Tamamlanan toplam |
| checkpoint_queue.pending_due | **2.048** | Vadesi gelmiş bekleyen iş |
| checkpoint_queue.leased | 1 | Aktif gibi görünen lease |
| checkpoint_queue.expired_leases | **1** | Yakından incelenecek |
| checkpoint_queue.superseded | 22 | Eski/yerine yenisi gelen |
| checkpoint_queue.waiting_data | 0 | Bu özet alanında 0 |
| checkpoint_queue.t6_base_completed | 25 | T-6 BASE tamamlamaları |
| checkpoint_queue.oldest_due_seconds | ~269.025 | Kuyrukta uzun gecikme var |
| historical_pending_due | 2.323 | Tarihsel bekleyen iş istatistiği; **silme talimatı değil** |
| reconciliation_queue.total | 21 | Reconciliation işleri |
| reconciliation_queue.pending_due | 21 | Henüz temizlenmemiş |
| reconciliation_queue.completed | 0 | — |
| reconciliation_queue.waiting_data | 21 | Kaynak eksikliği/erteleme |
| fixture_identity.drift_events | 60 | Maç kickoff/identity drift kaydı |

Discovery cursor:
- `initialized=true`
- `last_scanned_at=2026-10-24T01:40:40.487139+00:00`
- `completed_through=2026-10-27T03:40:40.34442+00:00`
- **Ayrı fixture discovery servisi bu cursor'u güncellemiyor olabilir**, kapsama sorgusunu esas al.

## 7.2 Gelecek 80 saatteki fixture kapsamı

Bağımsız SQL sorgusu (`public.fixtures` + V3 aktif checkpoint işlerinin join'i):

| Kontrol | 24 Ekim sonucu |
| --- | ---: |
| Gelecek 80 saat içindeki fixture | **853** |
| Her biri için 11 işin 11'i bulunan fixture | **853** |
| Eksik checkpoint job seti olan fixture | **0** |
| Bu fixture'lar için toplam aktif checkpoint job | **9.383** |

**Sonuç:** Gelecek maçları **keşfetme ve 11/11 iş yaratma** problemi bu anda giderilmiş. Bir önceki okumada ~852 maçtan yalnız 540'ının 11 iş seti tam, 312'si eksikti; aktivasyon sonrası 853/853 oldu. Fakat bu sayı **işleri işleme veya sinyal üretme başarısı değildir**.

## 7.3 Ana worker neden hâlâ kapalı?

Son doğrudan Hetzner salt-okunur tanı: **24 Ekim 02:27:48 UTC**
- `smartxflow-base-worker.service`: `ActiveState=failed`
- `ExecMainStatus=3`, `Result=exit-code`
- `smartxflow-base-guarded-recovery.timer`: `active` ve `enabled`
- Guard journal: `RECOVERY_STARTED` ve tekrarlanan `SKIP_COOLDOWN` gördü.
- Worker ~01:41:39 UTC döngüsünde: `lease_uncertain=1`, `claimed=3`, `skipped_data=2`, `healthy_cycle=false`, ardından exit code 3.
- 02:34:26 UTC başarılı Hetzner deploy logu dahi `AUTONOMOUS_BASE_OPERATOR_REVIEW: enabled but stopped; not auto-restarting` dedi.
- Supabase `completed=301` daha sonra artmadı; `pending_due=2048`. Dolayısıyla **worker'ın backlog'u güvenilir biçimde tükettiği kanıtlanmamıştır.**
- 02:34 sonrasında yeni `systemctl` tanısı yoktur. “Şu saniye de hâlâ failed” iddiası ancak yeni ölçümle kurulabilir.

**Muhtemel teknik odak:** Lease/ACK belirsizliği. Veritabanı RPC'si başarıyla commit edilmiş fakat yanıtı kaybolmuş olabilir; retry yaptığında çift işleme/yarım işleme oluşturma riski var. Error code 3 güvenlik freni durumu görünür kılıyor. Bu fren nedensizce kapatılmamalı.

Koruma davranışı: `scripts/base_worker_guarded_recovery.py` stop code 3, 1800 saniye cooldown, en fazla 30 gün sınırı, onaylı env flags ve üç ayrı DB lease tablosunda canlı lease olmaması gibi önkoşulları doğrulayıp yalnız uygun durumda `systemctl reset-failed` ve `start` yapıyor. Eksik/şüpheli bilgi olduğunda `SKIP` etmesi amaçlanmış güvenlik davranışı.

Ana worker'a ait manuel, korumalı GitHub workflow: `.github/workflows/base-autonomous-hetzner-enable.yml`, **workflow_dispatch only**. Açıkça onaysız veya preflight'ı ihlal ederek otomatik `push` üzerinden devreye alınmayacak. 24 Ekim bu dosyanın kontrolü düzeltildi, **aktivasyonu çalıştırılmadı veya başarıyla doğrulanmadı**.

# 8. Yeni sohbette izlenecek gerçekçi çözüm sırası

1. **Önce salt-okunur doğrulama:** Güncel `main`/`preview` HEAD, kaynak sözleşmeler ve yeni commitler; Hetzner `systemctl show/status` base worker, guard timer, discovery service; son `journalctl` (sanitized); Supabase health ve gerçek `lease` durumları.
2. **Hatanın kökü:** `lease_uncertain` nereden geliyor? RPC ACK kaybı, lease fencing/token, timeout, SQL/DB bağlantı problemi veya `skip_missing_source` sonrası belirsiz ACK mi? Gerçek `claimed` / `completed` / `skipped_data` cycle izini doğru korele et.
3. **Hedefli düzeltme:** Duraklayan döngüyü çöz; idempotence ve lease fencing'i koru. “Bütün işleri sil/yeniden yarat”, snapshot temizliği, geçmiş veri kaybı veya güvenlik freni körlemesine kaldırılması yasak. Eksik veri yalnız o fixture/checkpoint'i güvenli skip yapsın.
4. **Test ve sürüm politikası:** Önce preview'de kod+unit/integration tests; preflight güvenlik gate'i. Bu arada main değişirse normal PR merge ile koru, production güncellemesi için release sözleşmesi ve **yeni açık onay** kontrolü.
5. **Tek ve doğru worker'ı devreye alma:** Manual-only korumalı workflow ya da sözleşmenin açıkça izin verdiği guard/recovery yolunu kullan; `smartxflow-sinyal.service` eski ve kapalı kalmalı. Keşif servisini tekrar legacy'e bağlama.
6. **Kalıcı canlı teyit:** İki/çoklu gerçek cycle boyunca `ActiveState=active`, `healthy_cycle=true`, `lease_uncertain=0`; `completed` zamanla artıyor, `pending_due` yaşlanan işlerden azalıyor; SLA ve yeterli tarama kapasitesi ölçülüyor. Discovery `active/enabled`, 80 saat kapsamı 11/11; eski legacy `inactive/disabled`. Üretim API'de sinyaller görünür, çift yaratım yok.
7. **Dürüst durum raporu:** Geçerli kuyruk/gelecek maçlar, geçmiş veri koruma, expected/actual worker throughput, 24 saatlik 7/24 süreklilik kanıtları net ayrılmalı; “çalışıyor” ancak canlı ölçümle söylenmeli.

## Kabul kriterleri

- Veri kaybı **0**; hiçbir maç/snapshot/sinyal/tarihsel kuyruk kaydı silinmedi.
- Güncel V3'e göre gelecek maçların **11/11 job seti** eksiksiz.
- Eski dedicated sinyal servisi **inactive/disabled**; tek güncel hesaplama worker.
- Ana worker güvenli biçimde **aktif**, çalışma döngüleri sağlıklı, iş bitiş sayısı artıyor, due backlog küçülüyor.
- Yeni data snapshotlarıyla gelecek fikstürler otomatik keşfedilmeye devam ediyor; agentsiz çalışma.
- `preview`/`main` ve Hetzner deployed SHA **açıkça raporlanmış** ve korumalı release akışına uygun.
- Güncel UI'de tek motor ve ilgili sinyal kartları; yanlış/expired HEAVY gösterimlerinin bağımsız doğrulaması.
- Replit/kişisel PC'ye dokunulmadı.

# 9. Eylem ve test bağlantıları

- Proje: https://github.com/hazardyk27-sudo/smartxflow
- PR #64: https://github.com/hazardyk27-sudo/smartxflow/pull/64
- PR #65: https://github.com/hazardyk27-sudo/smartxflow/pull/65
- PR #66: https://github.com/hazardyk27-sudo/smartxflow/pull/66
- Son Hetzner production deploy run: https://github.com/hazardyk27-sudo/smartxflow/actions/runs/40054698927
- Ayrı discovery aktivasyonu run: https://github.com/hazardyk27-sudo/smartxflow/actions/runs/40054698943
- Base motor CI (başarılı): https://github.com/hazardyk27-sudo/smartxflow/actions/runs/40054511930
- Source preflight (başarılı): https://github.com/hazardyk27-sudo/smartxflow/actions/runs/40054556381
- Worker tanıları: https://github.com/hazardyk27-sudo/smartxflow/actions/runs/40054166399 ve https://github.com/hazardyk27-sudo/smartxflow/actions/runs/40054240551

# 10. Aynen aktarılacak kullanıcı isteği (özet, öncelik sırası)

> “Artık tek güncel sinyal motoru çalışsın; eski V2/V3 ayrımı ve eski sinyal servisi olmasın. Hiçbir maç, veri, snapshot ve sinyal kaydını silme. Motor önce birikmiş geçerli işleri tüketsin, sonra gelecekteki maçları gün/gün kronolojik tarasın, eksik veri için sadece ilgili maçı atlayabilsin. Agentsiz 7/24 çalışsın. GitHub main/preview normal merge ile yeni değişiklikleri kaybetmeden senkron kalsın, Hetzner son onaylı sürüme gelsin; Replit'e ve PC'ye dokunma. En önemlisi ana worker'ı güvenli biçimde gerçekten çalıştır ve **üretimde doğrula**; sadece CI başarılı diye tamam demeyin.”

**Son durum tek cümle:** 24 Ekim 05:43 Türkiye saati itibarıyla production kod/sürüm ve **bağımsız gelecek maç keşfi** başarılı (853/853 fixture, 11'er job), **ANA BASE WORKER ise lease belirsizliği sebebiyle henüz sağlıklı 7/24 çalıştığı kanıtlanmamış ve due kuyruk bekliyor**.

---

**Yeni sohbete yapıştırılabilecek kısa başlangıç metni:**

“GitHub `hazardyk27-sudo/smartxflow` reposundaki `docs/SMARTXFLOW_TAM_DEVIR_2026-10-24.md` belgesini baştan sona oku. İçindeki güncel kuralları ve kullanıcı izin sınırlarını koru. 24 Ekim 05:43 İstanbul doğrulamasında fixture discovery 853/853 tam ama ana Base worker exit code 3 / `lease_uncertain=1`, `completed=301`, `pending_due=2048`. Önce güncel sistem ve kaynakları salt-okunur doğrula, lease ACK kaybını gider; veri silme, eski sinyal servisini açma, Replit ve PC'ye dokunma. Yetkili release akışına göre test edip production'da çalışan tek güncel sinyal motorunu ölçerek doğrula. Kaydedilmiş durumu eksiksiz ve dürüstçe raporla.”
