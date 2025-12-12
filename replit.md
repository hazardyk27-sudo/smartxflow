# SmartXFlow Monitor – Odds & Volume Tracker

### Overview
SmartXFlow Monitor is a professional betting odds tracking tool designed to scrape Moneyway and Dropping Odds data, store it as time series, and provide graphical analysis. The project aims for a zero-cost, 24/7 data collection and visualization solution through a hybrid architecture, minimizing reliance on Replit's free tier limitations. It functions as a pure data collection and visualization tool, with alarm calculations handled by a separate PC-based application and displayed on the web/desktop UI.

### User Preferences
- **DEĞİŞİKLİK YAPMADAN ÖNCE SOR** - Hiçbir dosyaya dokunmadan önce kullanıcıdan onay al
- **SADECE İSTENENİ YAP** - Kendi fikirlerini ekleme, özellikle alarmlar konusunda kullanıcının talebine uy
- **ANLAMADIĞINDA SOR** - Varsayım yapma, netleştirmek için kullanıcıya danış
- **KURALLARA UY** - replit.md'deki tüm kurallara harfiyen uy
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
- **Standalone Scraper (PC-based):** A Python application (`SmartXFlow Admin Panel v1.04`) scrapes data and calculates alarms, writing them directly to Supabase.
- **Web UI (Replit-based):** A Flask web application reads and displays alarms from Supabase. Scraper functionality is disabled in this environment.
- **Desktop Application:** A PyInstaller-built application (`SmartXFlowDesktop.exe`) provides a native UI by embedding a local Flask backend within a pywebview window.

**Technology Stack:**
- **Language:** Python 3.11
- **Web UI:** Flask, Jinja2, Chart.js
- **Database:** Supabase (PostgreSQL)
- **Scraping:** `requests`, `BeautifulSoup`
- **Build Tool:** PyInstaller
- **CI/CD:** GitHub Actions

**Features & Specifications:**
- **Data Collection:** Supports 6 markets (1X2, O/U 2.5, BTTS for Moneyway and Dropping Odds).
- **Web UI:** Dark theme, Chart.js graphs, match detail modals.
- **Alarm Grouping:** Alarms for the same match, type, and market/selection are grouped, showing the latest alarm and history.
- **Timezone:** All timestamps are stored in UTC in the backend/DB. Frontend displays in `Europe/Istanbul`.
- **Scrape Interval:** Fixed at 10 minutes.
- **Prematch System:** Only prematch data is tracked. No data is recorded for matches once they start or for dates older than D-1.
- **API Optimization:**
    - `/api/alarms/all`: Batch endpoint for all 7 alarm types, with client-side caching (45s TTL).
    - `/api/match/<match_id>/snapshot`: Endpoint for all data related to a single match (alarms, metadata, moneyway, dropping_odds). Uses a 12-character MD5 hash `match_id`.

**Supabase Tables (Phase 2):**
- `fixtures`: Stores match metadata with a unique `match_id_hash`.
- `moneyway_snapshots`: Stores time-series moneyway data for matches.
- `dropping_odds_snapshots`: Stores time-series dropping odds data for matches.

**Alarm Table Schema (Example for Sharp Alarm Fields):**
- Hacim: `amount_change`, `avg_last_amounts`, `shock_raw`, `shock_value`, `volume_multiplier`, `max_volume_cap`, `volume_contrib`
- Oran: `previous_odds`, `current_odds`, `drop_pct`, `odds_multiplier_base`, `odds_multiplier_bucket`, `odds_multiplier`, `odds_value`, `max_odds_cap`, `odds_contrib`
- Pay: `previous_share`, `current_share`, `share_diff`, `share_multiplier`, `share_value`, `max_share_cap`, `share_contrib`
- Skor: `sharp_score`

### External Dependencies
- **arbworld.net:** Primary data source for betting odds.
- **Supabase:** Cloud-based PostgreSQL for all data storage.
- **GitHub Actions:** Used for continuous integration and deployment, specifically for automated .exe builds.