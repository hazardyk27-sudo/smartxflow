# SmartXFlow Monitor – Odds & Volume Tracker

## Overview
SmartXFlow Monitor is a professional betting odds tracking tool designed for collecting and visualizing Moneyway and Dropping Odds data as time series. The project aims to provide a zero-cost, 24/7 data collection and visualization solution through a hybrid architecture, minimizing reliance on free-tier limitations. It focuses purely on data collection and visualization, with alarm calculations handled by a separate PC-based application. The business vision is to offer a comprehensive, real-time data monitoring solution for betting markets with high market potential among professional bettors and analysts.

## User Preferences
- DEĞİŞİKLİK YAPMADAN ÖNCE SOR
- SADECE İSTENENİ YAP
- ANLAMADIĞINDA SOR
- KURALLARA UY
- DESKTOP UI'A DOKUNMA - Kullanıcı söyleyene kadar sadece mobil (@media max-width: 768px) değişiklik yap
- GITHUB KULLANICI ADI: hazardyk27-sudo
- UYGULAMA = app.py (web), desktop/desktop_app.py (standalone)
- SCRAPER'A DOKUNMA
- SADECE "push et" DENDIGINDE
- SADECE UYGULAMA DOSYALARI
- PUSH KOMUTU: `git push --force` kullan
- DEBUG DOSYASI
- SUPABASE SECRET ADI - Her zaman SUPABASE_ANON_KEY kullan
- WEB URL: https://ea61a90d-fbe5-4a43-993a-4a7ea861590b-00-el7p3v8o3jsj.janeway.replit.dev/
- BREAKPOINT KURALI: Kullanıcı "16:9" veya "full" veya "full size" dediğinde `@media (min-width: 1920px)` breakpoint'ini değiştir. Kullanıcı ayrıca belirtmedikçe diğer breakpoint'lere DOKUNMA.
- ALARM CALC STATUS KURALI: Her alarm türü için AYRI CalcStatus elementi olmalı:
  - Sharp: `calcStatus`, `calcProgress` elementleri + `showCalcStatus()`, `hideCalcStatus()` fonksiyonları
  - Insider: `insiderCalcStatus`, `insiderCalcProgress` elementleri + `showInsiderCalcStatus()`, `hideInsiderCalcStatus()` fonksiyonları
  - BigMoney: `bigMoneyCalcStatus`, `bigMoneyCalcProgress` elementleri + `showBigMoneyCalcStatus()`, `hideBigMoneyCalcStatus()` fonksiyonları
  - Yeni alarm eklendiğinde: `[alarmName]CalcStatus`, `[alarmName]CalcProgress` + `show[AlarmName]CalcStatus()`, `hide[AlarmName]CalcStatus()` oluştur

## System Architecture

**Core Architecture:**
The system employs a hybrid architecture with Supabase serving as the single source of truth for alarms. A standalone PC-based Python application scrapes data and calculates alarms, writing them directly to Supabase. A Flask web application (Replit-based) reads and displays these alarms. Scraping functionality is disabled in the web application.

**Technology Stack:**
- **Language:** Python 3.11
- **Web UI:** Flask, Jinja2, Chart.js
- **Database:** Supabase (PostgreSQL)
- **Scraping:** `requests`, `BeautifulSoup`
- **Build Tool:** PyInstaller
- **CI/CD:** GitHub Actions

**Features & Specifications:**
- **Data Collection:** Supports 6 markets (1X2, O/U 2.5, BTTS for Moneyway and Dropping Odds).
- **Web UI:** Features a dark theme, Chart.js graphs for data visualization, and match detail modals.
- **Onboarding Tutorial:** Provides a first-visit step-by-step tutorial overlay, highlighting key UI elements.
- **Alarm Grouping:** Alarms for the same match, type, and market/selection are grouped, displaying the latest alarm and its history.
- **Timezone Handling:** All backend/DB timestamps are UTC; the frontend displays time in `Europe/Istanbul`.
- **Prematch System:** Only prematch data is tracked; no data for in-play or past matches.
- **Telegram Notifications:** Real-time alarm notifications via a Telegram bot with configurable per-alarm-type enable/disable, retrigger support, deduplication, and visual card notifications.
- **Analysis-Match Linking:** Allows linking analyses to matches via a `match_id_hash`, displaying a star indicator for matches with analyses, and providing an analysis modal.
- **API Optimization:** Includes batch endpoints for alarm types with client-side caching, a comprehensive snapshot endpoint for all match-related data, and a Full CSV export that downloads all 6 markets (Moneyway + Dropping for 1X2/OU25/BTTS), all snapshots, money/percentage/odds data, and alarm records in a single file.
- **Supabase Request Optimization:** Implements server-side caching, prevents auto-refresh for background tabs, and uses jitter to prevent synchronized spikes.
- **Performance Optimization:** Features lazy warmup for sections, static asset caching, Gzip compression, CSS/JS minification (via `.src` files and `minify.py`), smart rendering for different devices, parallel preloading of market data, and optimized polling for admin interfaces.
- **Multi-Analyst System:** Supports multiple analysts with dedicated profiles, CRUD operations via API, automated success rate calculation (including ROI and Net Profit metrics using 1-unit flat stake model), and integration into the admin panel and frontend.
- **Mobile Filter Modal:** Replaces the old mobile dropdown with a dedicated filter modal for date, sorting, and filtering options.
- **Process Isolation:** The system is designed with three independent processes (`app.py`, `run_services.sh` for Scraper/Alarm Engine supervisor), ensuring that the failure of one does not affect others.
- **Live (Canlı) System:** A separate `live_scraper.py` runs every 1 minute, fetching live odds and money data from **Betwatch.fr** (Betfair exchange data via JSON API: `getMoney` for volume/money + `getMain` for 1X2 odds), enriched with real-time score and minute data from **Sofascore API** (`api.sofascore.com/api/v1/sport/football/events/live`). Betwatch provides: Betfair back/lay odds, selection-level money (£), total market volume, Match Odds + Over/Under markets. Data stored in `live_fixtures` and `live_snapshots` Supabase tables. The "Canlı" tab in the UI (desktop + mobile) shows live matches with odds, O/U line, volume, real-time minute and score, and a detail modal with period-by-period snapshot history. Auto-refreshes every 30 seconds. Source key: `replit-live`. D-2 cleanup applies to live tables. Prematch data still uses Arbworld.
- **Data Model:** Uses `fixtures`, `moneyway_snapshots`, `dropping_odds_snapshots`, `live_fixtures`, and `live_snapshots` tables in Supabase.
- **match_id_hash Contract:** A critical, immutable contract defines `match_id_hash` as a 12-character MD5 hash of a canonical string (`league|home|away`), with specific normalization rules. Kickoff/date is explicitly excluded from hash calculation.
- **Endpoint Response Contract:** The `/api/match/<match_id_hash>/snapshot` endpoint has an immutable response structure, ensuring backward compatibility, allowing only the addition of new fields or nested objects.

## External Dependencies
- **arbworld.net:** Primary data source for betting odds.
- **Supabase:** Cloud-based PostgreSQL database for all data storage.
- **GitHub Actions:** Used for continuous integration and deployment, specifically for automated .exe builds.