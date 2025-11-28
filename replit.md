# SmartXFlow Alarm V1.01 – Odds & Volume Monitor

### Overview
SmartXFlow Alarm is a professional betting analysis tool designed to scrape Moneyway and Dropping Odds data from arbworld.net, store it as time series, and provide graphical analysis. It identifies "Smart Money" movements in sports betting markets to provide users with an edge. The project aims for a zero-cost, 24/7 data collection and analysis solution through a hybrid architecture, minimizing reliance on Replit's free tier limitations.

### User Preferences
- **UYGULAMA = desktop_app.py** - "uygulama" dendiğinde HER ZAMAN desktop_app.py build edilir (pywebview masaüstü)
- **SCRAPER'A DOKUNMA** - scraper_standalone/ klasorune ve build_scraper.yml'e dokunma, zaten calisiyor
- **SADECE "push et" DENDIGINDE** push yap, otomatik push yapma
- **SADECE UYGULAMA DOSYALARI** push et (app.py, templates, static, core, services)
- **PUSH KOMUTU:** `git push --force` kullan (conflict varsa)
- **DEBUG DOSYASI** - Her EXE build'inde BUILD_INFO.txt ve smartxflow_debug.log dahil edilir
- **SUPABASE SECRET ADI** - Her zaman SUPABASE_ANON_KEY kullan (SUPABASE_KEY değil)

### System Architecture

**Core Architecture:**
The system uses a hybrid architecture:
- **Standalone Scraper (PC-based):** A Python application (`SmartXFlow Alarm V1.01Scraper.exe`) runs on a Windows PC, scraping data from arbworld.net every 10 minutes and directly writing it to Supabase. This ensures continuous data collection even if the Replit environment is dormant.
- **Web UI (Replit-based):** A Flask web application hosted on Replit acts as a read-only interface. It fetches data from Supabase and displays it graphically. The scraper functionality is explicitly disabled in the Replit environment (`DISABLE_SCRAPER=true`).
- **Desktop Application:** A PyInstaller-built desktop application (`SmartXFlowDesktop.exe`) provides a native user experience. It embeds a Flask backend running locally (127.0.0.1:5000) within a pywebview (Edge WebView2) window, eliminating the need for external browser tabs or console windows.

**Technology Stack:**
- **Language:** Python 3.11
- **Web UI:** Flask, Jinja2, Chart.js
- **Database:** Supabase (PostgreSQL - cloud)
- **Scraping:** `requests`, `BeautifulSoup`
- **Build Tool:** PyInstaller (for Windows .exe)
- **CI/CD:** GitHub Actions (for automated .exe builds)

**Features:**
- **Data Collection (6 Markets):**
    - Moneyway Markets: 1X2, O/U 2.5, BTTS
    - Dropping Odds Markets: 1X2, O/U 2.5, BTTS
- **Web UI:** Modern dark theme (GitHub style), Chart.js graphs, match detail modals, Smart Money Alarm System, Ticker animation.
- **Smart Money Alarm System:** Detects various betting market anomalies:
    - **Reverse Line Move (RLM):** Significant money inflow opposite to odds movement.
    - **Sharp Move:** Significant money inflow with odds drop.
    - **Big Money Move:** Large money inflow within a short period, regardless of odds movement.
    - **Line Freeze**
    - **Public Money Surge**
    - **Momentum Spike**
    - **Momentum Change:** Shift in market dominance.
- **Alarm Safety System:**
    - **Append-Only Storage:** Alarms are never deleted or overwritten.
    - **Idempotent Deduplication:** Prevents duplicate alarms using a unique fingerprint.
    - **Periodic Self-Check (Reconciliation):** Hourly check for missing alarms.
    - **Error Logging + Retry:** Failed alarm insertions are logged and retried.
    - **Safety Check Endpoint:** Verifies system integrity.
    - **AlarmSafetyGuard:** Wrapper for all alarm records with exception handling and logging.
    - **Reconciliation Endpoint:** Manual trigger for alarm reconciliation.

**Technical Specifications:**
- **Timezone:** Turkey (Europe/Istanbul) is consistently used across the application.
- **Scrape Interval:** Fixed at 10 minutes.
- **Data Formats:** Trend as "up"/"down", volume with "£" and thousands separator, date/time as DD.MM.YYYY HH:MM (Turkey time).

---

## REFERANS DOKÜMANI - PREMATCH SİSTEMİ KURALLARI

### 1. Temel Prensip: Prematch Sistemi (Canlı Değil)
- Uygulama CANLI MAÇ VERİSİYLE ÇALIŞMIYOR
- Sadece maç başlamadan önceki para & oran hareketleri takip ediliyor
- Maç başladıktan sonra: Yeni odds/stake kaydı OLMAMALI, yeni alarm ÜRETİLMEMELİ

### 2. Arbworld Entegrasyonu
- Arbworld, maç başladığında o maçı listeden kaldırır
- Arbworld'de görünmeyen maç = "Bitti, sadece geçmiş verisi okunur"
- Scraper: Arbworld listesinden kalkan maçlara veri YAZMAMALI

### 3. Tarih Bazlı Yaşam Döngüsü (TR Saati)

| Gün | Tanım | UI | Veri Yazma | Alarm Üretme |
|-----|-------|----|-----------:|-------------:|
| **D** (Bugün) | `fixture_date == today` | "Günün Maçları" | Arbworld'deyse EVET | EVET |
| **D-1** (Dün) | `fixture_date == yesterday` | "Dünün Maçları" | HAYIR | HAYIR (sadece statik) |
| **D-2+** (Eski) | `fixture_date <= D-2` | GÖSTERİLMEZ | HAYIR | SİL/ARŞİVLE |

### 4. Veri Güvenliği Kuralları
```
when inserting odds_history row:
    if fixture_date < D: REJECT (dünkü/eski maça veri yazma)
    if fixture_date == D and match not in arbworld: REJECT (başlamış)

when evaluating alarms:
    only consider: fixture_date == D AND match in arbworld list
```

### 5. Timezone Sistemi - TEK KAYNAK KURALI

**Backend / DB:**
- Tüm timestamp'ler UTC olarak saklanır
- Fields: `kickoff_utc`, `timestamp_utc`, `triggered_at_utc`, `scraped_at_utc`

**Frontend:**
- Varsayılan timezone: `Europe/Istanbul`
- Tüm tarih/saat gösterimleri: `dayjs.utc(...).tz('Europe/Istanbul')`
- Uygulanan yerler: Maç saati, Son Güncelleme, Grafik X ekseni, Tooltip, Alarm Listesi, Alarm Geçmişi

### 6. Alarm Kuralları

**A. Alarm Saatleri:**
- `triggered_at_utc` → UI'de TR saati olarak gösterilir
- Alarm Listesi, Alarm Geçmişi, Maç Detayı → AYNI helper kullanır

**B. Alarm Tutarlılığı:**
- Alarm Listesi sorgusu = Maç Detayı alarm sorgusu
- Aynı `match_id + type` filtreleri kullanılmalı

**C. Big Money & Dropping Mantığı:**
- Big Money: `delta stake = stake_curr - stake_prev` (TOTAL DEĞİL)
- Dropping: Oran değişimi YOKSA alarm tetiklenmemeli

### 7. Update Politikası

Timezone/tarih mantığına dokunan her update için:
1. Merge/publish öncesi kontrol edilecek alanlar:
   - Maç listesi saatleri
   - Son Güncelleme alanı
   - Grafik tooltip saatleri
   - Alarm Listesi saatleri
   - Maç detayı alarm saatleri
2. Başka modüllerde değişiklik gerekiyorsa → HABER VER
3. Değişiklik notu (changelog) yaz

---

### External Dependencies
- **arbworld.net:** Source for Moneyway and Dropping Odds data.
- **Supabase:** Cloud-based PostgreSQL database for data storage and retrieval.
- **GitHub Actions:** CI/CD for automated builds.