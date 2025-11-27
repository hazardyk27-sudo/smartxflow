# SmartXFlow Alarm V1.01 – Odds & Volume Monitor

## Proje Ozeti
Windows masaustu uygulamasi - arbworld.net'ten Moneyway ve Dropping Odds verilerini cekip, zaman serisi olarak saklayan ve grafiksel analiz sunan profesyonel bahis analiz araci.

## Mimari: Standalone Scraper + Web UI

### YENİ MİMARİ (26 Kasım 2025)
```
┌─ PC (SmartXFlow Alarm V1.01Scraper.exe) ────────────────────┐
│  Standalone Scraper (10dk)                       │
│  arbworld.net → Supabase (direkt yazma)          │
│  Windows'ta arkaplanda çalışır                   │
└──────────────────────────────────────────────────┘
                        ↓
                   [Supabase]
                        ↓
┌─ REPLIT (Web UI) ───────────────────────────────┐
│  Flask Web Arayüzü                               │
│  Supabase'ten okur (READ-ONLY)                   │
│  Scraper YOK - sadece görüntüleme                │
│  DISABLE_SCRAPER=true                            │
└──────────────────────────────────────────────────┘
```

### Neden Bu Mimari?
- Replit free tier ~5 dakika sonra uyku moduna giriyor
- PC'de çalışan scraper 7/24 veri toplar
- Replit uyusa bile veriler toplanmaya devam eder
- Maliyet: $0 (Replit deploy gereksiz)

## Teknoloji Stack
- **Dil:** Python 3.11
- **Web UI:** Flask + Jinja2 + Chart.js
- **Database:** Supabase (PostgreSQL - cloud)
- **Scraping:** requests + BeautifulSoup (arbworld.net)
- **Build Tool:** PyInstaller (Windows .exe)
- **CI/CD:** GitHub Actions (otomatik .exe build)

## Proje Yapisi
```
.
├── app.py                # Flask Web Backend
├── desktop_app.py        # Masaüstü Uygulaması (pywebview wrapper)
├── scraper_standalone/   # PC Scraper (bağımsız)
│   ├── standalone_scraper.py  # Ana scraper script
│   ├── config.json            # Supabase ayarları
│   ├── requirements.txt       # Bağımlılıklar
│   └── README.md              # Kurulum talimatları
├── scraper/              # Eski Replit scraper (devre dışı)
│   ├── __init__.py
│   ├── core.py
│   └── moneyway.py
├── services/
│   └── supabase_client.py
├── core/
│   ├── settings.py       # Mode + DISABLE_SCRAPER kontrolü
│   ├── alarms.py         # Smart Money alarm mantığı
│   └── storage.py
├── templates/
├── static/
├── .github/workflows/
│   ├── build.yml              # SmartXFlowDesktop.exe (Masaüstü)
│   └── build_scraper.yml      # SmartXFlowScraper.exe
└── replit.md
```

## Desktop Uygulama Mimarisi
```
┌─ SmartXFlowDesktop.exe ─────────────────────────────┐
│  pywebview (Edge WebView2)                          │
│  ├── Flask backend (127.0.0.1:5000)                 │
│  ├── Gömülü tarayıcı penceresi                      │
│  └── Konsol yok, harici tarayıcı yok                │
└─────────────────────────────────────────────────────┘
```
- Çift tıklayınca tek bir masaüstü penceresi açılır
- Tarayıcı sekmesi açılmaz
- Konsol görünmez
- Tüm mantık lokal (127.0.0.1)

## Kurulum

### 1. Supabase Tabloları
```sql
-- Ana tablolar
CREATE TABLE moneyway_1x2 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Odds1 TEXT, OddsX TEXT, Odds2 TEXT, Pct1 TEXT, Amt1 TEXT, PctX TEXT, AmtX TEXT, Pct2 TEXT, Amt2 TEXT, Volume TEXT);
CREATE TABLE moneyway_ou25 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Under TEXT, Line TEXT, Over TEXT, PctUnder TEXT, AmtUnder TEXT, PctOver TEXT, AmtOver TEXT, Volume TEXT);
CREATE TABLE moneyway_btts (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Yes TEXT, No TEXT, PctYes TEXT, AmtYes TEXT, PctNo TEXT, AmtNo TEXT, Volume TEXT);
CREATE TABLE dropping_1x2 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Odds1 TEXT, Odds1_prev TEXT, OddsX TEXT, OddsX_prev TEXT, Odds2 TEXT, Odds2_prev TEXT, Trend1 TEXT, TrendX TEXT, Trend2 TEXT, Volume TEXT);
CREATE TABLE dropping_ou25 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Under TEXT, Under_prev TEXT, Line TEXT, Over TEXT, Over_prev TEXT, TrendUnder TEXT, TrendOver TEXT, PctUnder TEXT, AmtUnder TEXT, PctOver TEXT, AmtOver TEXT, Volume TEXT);
CREATE TABLE dropping_btts (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, OddsYes TEXT, OddsYes_prev TEXT, OddsNo TEXT, OddsNo_prev TEXT, TrendYes TEXT, TrendNo TEXT, PctYes TEXT, AmtYes TEXT, PctNo TEXT, AmtNo TEXT, Volume TEXT);

-- History tablolar (ScrapedAt ile)
CREATE TABLE moneyway_1x2_history AS SELECT *, '' AS ScrapedAt FROM moneyway_1x2 WHERE 1=0;
CREATE TABLE moneyway_ou25_history AS SELECT *, '' AS ScrapedAt FROM moneyway_ou25 WHERE 1=0;
CREATE TABLE moneyway_btts_history AS SELECT *, '' AS ScrapedAt FROM moneyway_btts WHERE 1=0;
CREATE TABLE dropping_1x2_history AS SELECT *, '' AS ScrapedAt FROM dropping_1x2 WHERE 1=0;
CREATE TABLE dropping_ou25_history AS SELECT *, '' AS ScrapedAt FROM dropping_ou25 WHERE 1=0;
CREATE TABLE dropping_btts_history AS SELECT *, '' AS ScrapedAt FROM dropping_btts WHERE 1=0;
```

### 2. PC Scraper Kurulumu
1. GitHub Actions'tan `SmartXFlow Alarm V1.01Scraper-Windows-EXE.zip` indir
2. Zip'i aç
3. `config.json` dosyasını düzenle (Supabase URL + Key)
4. `SmartXFlow Alarm V1.01Scraper.exe` çalıştır
5. Pencereyi minimize et (kapatma!)

### 3. Replit Ayarları
Environment variables:
- `SUPABASE_URL` - Supabase proje URL'i
- `SUPABASE_ANON_KEY` - Supabase anon key
- `DISABLE_SCRAPER=true` - Scraper devre dışı (UI-only mod)

## Environment Variables

| Değişken | Açıklama | Değer |
|----------|----------|-------|
| SUPABASE_URL | Supabase proje URL'i | https://xxx.supabase.co |
| SUPABASE_ANON_KEY | Supabase anon key | eyJ... |
| DISABLE_SCRAPER | Scraper'ı devre dışı bırak | true |
| SMARTXFLOW_MODE | Uygulama modu | server (otomatik) |

## Ozellikler

### Veri Toplama (6 Market)
1. **Moneyway Markets:** 1X2, O/U 2.5, BTTS
2. **Dropping Odds Markets:** 1X2, O/U 2.5, BTTS

### Web UI Özellikleri
- Modern dark theme (GitHub tarzı)
- Chart.js grafikleri
- Maç detay modal'ı
- Smart Money Alarm Sistemi
- Ticker animasyonu

### Smart Money Alarm Sistemi
1. 🔴 **Reverse Line Move (RLM)** - £3,000+ giriş + ters yönde oran hareketi
2. 🟢 **Sharp Move** - £3,000+ giriş + oran düşüşü
3. 💰 **Big Money Move** - 10 dakika içinde £15,000+ giriş (oran şartı yok)
4. 🔵 **Line Freeze**
5. 🟡 **Public Money Surge**
6. 🟣 **Momentum Spike**
7. 🔄 **Momentum Change** - Dominans değişimi (>50% pay değişimi)

## Teknik Notlar
- **Timezone:** Turkey (Europe/Istanbul) - Tüm uygulamada sabit
- **Timezone Modülü:** core/timezone.py - pytz kullanılıyor
- **Scrape Interval:** 10 dakika (sabit)
- **Trend Format:** "up" / "down" (API için)
- **Volume Format:** £ + binlik ayraç
- **Tarih Formatı:** DD.MM.YYYY HH:MM (Türkiye saati)

## Kullanici Tercihleri
- **UYGULAMA = desktop_app.py** - "uygulama" dendiğinde HER ZAMAN desktop_app.py build edilir (pywebview masaüstü)
- **SCRAPER'A DOKUNMA** - scraper_standalone/ klasorune ve build_scraper.yml'e dokunma, zaten calisiyor
- **SADECE "push et" DENDIGINDE** push yap, otomatik push yapma
- **SADECE UYGULAMA DOSYALARI** push et (app.py, templates, static, core, services)
- **PUSH KOMUTU:** `git push --force` kullan (conflict varsa)
- **DEBUG DOSYASI** - Her EXE build'inde BUILD_INFO.txt ve smartxflow_debug.log dahil edilir
- **SUPABASE SECRET ADI** - Her zaman SUPABASE_ANON_KEY kullan (SUPABASE_KEY değil)

## Son Guncellemeler
- **27 Kasim 2025:** 5dk grafik ölçeği kaldırıldı, minimum 10dk olarak ayarlandı
- **27 Kasim 2025:** "Dünün Maçları" butonu eklendi - toggle ile sadece biri aktif olabilir
- **27 Kasim 2025:** Eski maçları temizleme scheduler'ı eklendi (günde 1 kez)
- **27 Kasim 2025:** Alarm sistemi yeniden yazıldı: Tüm 10 dakikalık pencereler taranıyor (son 3 saat)
- **27 Kasim 2025:** WINDOW_MINUTES=10, LOOKBACK_MINUTES=180 - alarm thresholds config'e eklendi
- **27 Kasim 2025:** Türkiye saati (Europe/Istanbul) tüm uygulamada sabit - core/timezone.py modülü eklendi
- **27 Kasim 2025:** Alarm kuralları güncellendi: Sharp £3K + oran düşüşü, Big Money £15K/10dk, RLM £3K + ters oran
- **27 Kasim 2025:** Ticker kartları için benzersiz match_id navigasyonu - tıklanan kart her zaman doğru maçı açar
- **27 Kasim 2025:** match_id: home|away|league|date kombinasyonu ile tam benzersizlik
- **27 Kasim 2025:** Demo alarmlar eklendi (Sharp Money, Big Money, RLM, Line Freeze, Public Surge, Momentum)
- **26 Kasim 2025:** Standalone Scraper mimarisi - PC'de çalışan bağımsız .exe
- **26 Kasim 2025:** DISABLE_SCRAPER env variable - Replit'te scraper kapalı
- **26 Kasim 2025:** GitHub Actions scraper build workflow
- **26 Kasim 2025:** Supabase import hatası düzeltildi (core/storage.py)
- **26 Kasim 2025:** Scrape interval 10 dakikaya sabitlendi
- **26 Kasim 2025:** Turkey timezone (Europe/Istanbul)
- **26 Kasim 2025:** Smart Money Alarm Sistemi
- **25 Kasim 2025:** Flask Web UI + GitHub Dark tema
- **24 Kasim 2025:** Chart.js grafik entegrasyonu
