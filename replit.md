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
- **Data Model:** Uses `fixtures`, `moneyway_snapshots`, `dropping_odds_snapshots`, `live_fixtures`, and `live_snapshots` tables in Supabase. Atıl tablolar (eski PascalCase `_hist`, `alarm_config`, eski device-bazlı `match_favorites`) Task #156 kapsamında temizlendi; DROP TABLE migration: `migrations/2026_04_28_drop_orphan_tables.sql`.
- **Cleanup Policy:** `services/supabase_client.py:cleanup_old_matches` her gün 05:00 (Türkiye) çalışır, D-8'den eski (cutoff = today - 8d) snapshot/fixtures + 5 sinyal tablosu (confirmed_money, underdog, fake_sharp, confirmed_money_v2, early_money_lock) + `scraper_signal` (D-8) + `telegram_sent_log` (D-30) verisini siler. Manuel tetik: `POST /api/cleanup`.
- **match_id_hash Contract:** A critical, immutable contract defines `match_id_hash` as a 12-character MD5 hash of a canonical string (`league|home|away`), with specific normalization rules. Kickoff/date is explicitly excluded from hash calculation.
- **Test Mode:** Unlicensed users can try the app via "Ücretsiz Test Et" button on the license page (`session['license_plan'] = 'test'`). Test mode shows top 3 highest-volume matches on MW 1X2 and Oran 1X2 pages with full modal access (including live period data). Other markets (2.5, KG), Live tab, and Analysis page are locked. Alarm band shows all alarms but blurs selection+amount for non-free matches. Free match hashes fetched from `/api/test/free-matches`. No time limit, no registration required.
- **Endpoint Response Contract:** The `/api/match/<match_id_hash>/snapshot` endpoint has an immutable response structure, ensuring backward compatibility, allowing only the addition of new fields or nested objects.
- **SEO:** Meta description, OG tags, Twitter Card, canonical URL on all pages (landing, nedir, pricing, analysis, legal, app panel). JSON-LD structured data: Organization+WebSite on landing, FAQPage on pricing, CollectionPage on rehber hub, Article on rehber sub-pages. robots.txt + sitemap.xml served via Flask routes. App panel (index.html) has noindex/nofollow. Legal pages (terms, privacy, cookies, disclaimer) excluded from sitemap. Rehber is a hub page (`/rehber`) with 3 SEO sub-pages: `/rehber/oran-analizi`, `/rehber/para-hareketi`, `/rehber/canli-oran-takibi`. Old broken URLs (`/oran-analizi`, `/oran-degisimi`, `/canli-oran-takibi`, `/orani-dusen-maclar`, `/oran-ve-para-nasil-okunur`) redirect 301 to new sub-pages. Internal semantic links from landing and nedir pages to rehber hub.

## External Dependencies
- **arbworld.net:** Primary data source for prematch betting odds. Migrated from HTML scraping to JSON API on 2026-04-29 (`https://arbworld.net/api/get-runners.php?type={mw|do}&sport=soccer&order=date&market={MATCH_ODDS|OVER_UNDER_25|BOTH_TEAMS_TO_SCORE}&day=&lang=en`) after Arbworld switched its public site to a JS-driven SPA. The JSON returns `{success, count, data:[{date, leage, home, away, market_id, coef_1/x/2, coef_1_new/x_new/2_new, volume_1/x/2, ...}]}`. Outcome share (`pct1/x/2`) is derived as `volume_i / total_volume * 100`; `amt*` fields hold raw outcome volume formatted as `£ N`. Implementation: `desktop/scraper_standalone/standalone_scraper.py` (functions: `fetch_json`, `extract_*`). Auth not required; `User-Agent + Accept: application/json + X-Requested-With + Referer` headers are sufficient. Downstream Supabase tables, fixtures hash, and alarm engine pipeline unchanged. **Post-migration cleanup (Task #159, 2026-04-29):** The new JSON scraper returns full team names (e.g. "Atletico Madrid") whereas the old HTML scraper returned truncated names (e.g. "Atletico Ma"), producing different `match_id_hash` values and duplicate rows in the 6 main market tables. One-off script `scripts/one_off/cleanup_stale_arbworld_records.py` removed stale rows: it identifies "stale hashes" as those present in history tables before the cutoff but absent after (i.e. no longer written by the new scraper), then deletes matching rows from snapshot, history, main market, and fixtures tables. **Important schema note:** Main market tables (`moneyway_*`, `dropping_*`) have NO `scraped_at` or `match_id_hash` columns — only history (`*_history`) and snapshot (`moneyway_snapshots`) tables do. History `scraped_at` is stored as Turkey-tz string (`+03:00`); snapshot `scraped_at_utc` as UTC string — PostgREST does lex comparison on text columns, so cutoff strings must match the column's tz format.
- **Supabase:** Cloud-based PostgreSQL database for all data storage.
- **GitHub Actions:** Used for continuous integration and deployment, specifically for automated .exe builds.