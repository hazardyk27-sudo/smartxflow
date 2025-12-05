# SmartXFlow Monitor – Odds & Volume Tracker

### Overview
SmartXFlow Monitor is a professional betting odds tracking tool designed to scrape Moneyway and Dropping Odds data from arbworld.net, store it as time series, and provide graphical analysis. The project aims for a zero-cost, 24/7 data collection and visualization solution through a hybrid architecture, minimizing reliance on Replit's free tier limitations.

**Note:** The alarm/notification system has been removed. This is now a pure data collection and visualization tool (BANT system).

### User Preferences
- **GITHUB KULLANICI ADI:** hazardyk27-sudo (ASLA kcanmersin kullanma!)
- **UYGULAMA = desktop_app.py** - "uygulama" dendiğinde HER ZAMAN desktop_app.py build edilir (pywebview masaüstü)
- **SCRAPER'A DOKUNMA** - scraper_standalone/ klasorune ve build_scraper.yml'e dokunma, zaten calisiyor
- **SADECE "push et" DENDIGINDE** push yap, otomatik push yapma
- **SADECE UYGULAMA DOSYALARI** push et (app.py, templates, static, core, services)
- **PUSH KOMUTU:** `git push --force` kullan (conflict varsa)
- **DEBUG DOSYASI** - Her EXE build'inde BUILD_INFO.txt ve smartxflow_debug.log dahil edilir
- **SUPABASE SECRET ADI** - Her zaman SUPABASE_ANON_KEY kullan (SUPABASE_KEY değil)
- **ALARM CALC STATUS KURALI** - Her alarm türü için AYRI CalcStatus elementi olmalı:
  - Sharp: `calcStatus`, `calcProgress` elementleri + `showCalcStatus()`, `hideCalcStatus()` fonksiyonları
  - Insider: `insiderCalcStatus`, `insiderCalcProgress` elementleri + `showInsiderCalcStatus()`, `hideInsiderCalcStatus()` fonksiyonları
  - BigMoney: `bigMoneyCalcStatus`, `bigMoneyCalcProgress` elementleri + `showBigMoneyCalcStatus()`, `hideBigMoneyCalcStatus()` fonksiyonları
  - Yeni alarm eklendiğinde: `[alarmName]CalcStatus`, `[alarmName]CalcProgress` + `show[AlarmName]CalcStatus()`, `hide[AlarmName]CalcStatus()` oluştur

### System Architecture

**Core Architecture:**
The system uses a hybrid architecture with Supabase as the single source of truth for alarms:
- **Standalone Scraper (PC-based):** A Python application (`SmartXFlow Admin Panel v1.04`) runs on a Windows PC, scraping data from arbworld.net every 10 minutes and directly writing it to Supabase. The admin panel includes full alarm settings configuration with 7 alarm type tabs (Sharp, Public Move, Insider, Big Money, Dropping, Hacim Şoku, Hacim Lideri), allowing users to view/edit thresholds, multipliers, and alarm lists directly from the EXE. **Alarms are calculated by the EXE and written to Supabase alarm tables.**
- **Web UI (Replit-based):** A Flask web application hosted on Replit reads alarms from Supabase and displays them graphically. If Supabase alarm tables don't exist or are empty, falls back to local JSON files. The scraper functionality is explicitly disabled in the Replit environment (`DISABLE_SCRAPER=true`).
- **Desktop Application:** A PyInstaller-built desktop application (`SmartXFlowDesktop.exe`) provides a native user experience. It embeds a Flask backend running locally (127.0.0.1:5000) within a pywebview (Edge WebView2) window, eliminating the need for external browser tabs or console windows.

**Alarm Tables in Supabase:**
| Table Name | Alarm Type |
|------------|------------|
| sharp_alarms | Sharp Money |
| insider_alarms | Insider Info |
| bigmoney_alarms | Big Money |
| volumeshock_alarms | Hacim Şoku (Volume Shock) |
| dropping_alarms | Dropping Odds |
| publicmove_alarms | Public Move |
| volume_leader_alarms | Hacim Lideri (Volume Leader) |

**Important:** User must run `create_alarm_tables.sql` in Supabase Dashboard (SQL Editor) to create these tables before the EXE can write alarms. Until then, the system uses local JSON fallback.

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
- **Web UI:** Modern dark theme (GitHub style), Chart.js graphs, match detail modals.
- **Alarm Grouping:** Same match + alarm type + market/selection alarms are grouped into single card:
    - Latest alarm = current (shown in card header and alert band)
    - Previous alarms = history (shown when card is expanded)
    - History badge (×N) indicates total alarm count for that group
    - Functions: `groupAlarmsByMatch()`, `groupAlarmsForBand()`

**Technical Specifications:**
- **Timezone:** Turkey (Europe/Istanbul) is consistently used across the application.
- **Scrape Interval:** Fixed at 10 minutes.
- **Data Formats:** Trend as "up"/"down", volume with "£" and thousands separator, date/time as DD.MM.YYYY HH:MM (Turkey time).

---

## REFERANS DOKÜMANI - PREMATCH SİSTEMİ KURALLARI

### 1. Temel Prensip: Prematch Sistemi (Canlı Değil)
- Uygulama CANLI MAÇ VERİSİYLE ÇALIŞMIYOR
- Sadece maç başlamadan önceki para & oran hareketleri takip ediliyor
- Maç başladıktan sonra: Yeni odds/stake kaydı OLMAMALI

### 2. Arbworld Entegrasyonu
- Arbworld, maç başladığında o maçı listeden kaldırır
- Arbworld'de görünmeyen maç = "Bitti, sadece geçmiş verisi okunur"
- Scraper: Arbworld listesinden kalkan maçlara veri YAZMAMALI

### 3. Tarih Bazlı Yaşam Döngüsü (TR Saati)

| Gün | Tanım | UI | Veri Yazma |
|-----|-------|----|----------:|
| **D** (Bugün) | `fixture_date == today` | "Günün Maçları" | Arbworld'deyse EVET |
| **D-1** (Dün) | `fixture_date == yesterday` | "Dünün Maçları" | HAYIR |
| **D-2+** (Eski) | `fixture_date <= D-2` | GÖSTERİLMEZ | HAYIR |

### 4. Veri Güvenliği Kuralları
```
when inserting odds_history row:
    if fixture_date < D: REJECT (dünkü/eski maça veri yazma)
    if fixture_date == D and match not in arbworld: REJECT (başlamış)
```

### 5. Timezone Sistemi - TEK KAYNAK KURALI

**Backend / DB:**
- Tüm timestamp'ler UTC olarak saklanır
- Fields: `kickoff_utc`, `timestamp_utc`, `scraped_at_utc`

**Frontend:**
- Varsayılan timezone: `Europe/Istanbul`
- Tüm tarih/saat gösterimleri: `dayjs.utc(...).tz('Europe/Istanbul')`
- Uygulanan yerler: Maç saati, Son Güncelleme, Grafik X ekseni, Tooltip

---

### External Dependencies
- **arbworld.net:** Source for Moneyway and Dropping Odds data.
- **Supabase:** Cloud-based PostgreSQL database for data storage and retrieval.
- **GitHub Actions:** CI/CD for automated builds.