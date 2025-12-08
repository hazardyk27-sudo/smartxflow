# SmartXFlow Monitor – Odds & Volume Tracker

### Overview
SmartXFlow Monitor is a professional betting odds tracking tool designed to scrape Moneyway and Dropping Odds data from arbworld.net, store it as time series, and provide graphical analysis. The project aims for a zero-cost, 24/7 data collection and visualization solution through a hybrid architecture, minimizing reliance on Replit's free tier limitations.

**Note:** The alarm/notification system has been removed. This is now a pure data collection and visualization tool (BANT system).

### User Preferences

#### ÇALIŞMA KURALLARI (KRİTİK)
- **DEĞİŞİKLİK YAPMADAN ÖNCE SOR** - Hiçbir dosyaya dokunmadan önce kullanıcıdan onay al
- **SADECE İSTENENİ YAP** - Kendi fikirlerini ekleme, özellikle alarmlar konusunda kullanıcının talebine uy
- **ANLAMADIĞINDA SOR** - Varsayım yapma, netleştirmek için kullanıcıya danış
- **KURALLARA UY** - replit.md'deki tüm kurallara harfiyen uy

#### Genel Tercihler
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

**Important:** 
- İlk kurulum için: `create_alarm_tables_INITIAL_SETUP.sql` (V5.0) kullanın - TÜM TABLOLARI SİLİP YENİDEN OLUŞTURUR!
- Mevcut verileri koruyarak güncelleme için: `migrate_sharp_alarms_v5.sql` kullanın - SADECE YENİ ALANLAR EKLER

**ALAN ADI UYUMU (V5.0 - 2025-12-08):**
UI alan adları = tek kaynak (authoritative reference). Admin.exe ve Supabase bu alan adlarını kullanır:

**Sharp Alarm Formülleri:**
```
1. Hacim Şoku:
   - amount_change = curr_amt - prev_amt
   - avg_last_amounts = son 5 snapshot ortalaması (non-zero)
   - shock_raw = amount_change / avg_last_amounts
   - shock_value = shock_raw × volume_multiplier
   - volume_contrib = min(shock_value, max_volume_cap)

2. Oran Düşüşü:
   - drop_pct = ((prev_odds - curr_odds) / prev_odds) × 100
   - odds_value = drop_pct × odds_multiplier_bucket
   - odds_contrib = min(odds_value, max_odds_cap)

3. Pay Değişimi:
   - share_diff = curr_share - prev_share
   - share_value = share_diff × share_multiplier (negatif olabilir)
   - share_contrib = min(max(0, share_value), max_share_cap)

4. Final Skor:
   - sharp_score = volume_contrib + odds_contrib + share_contrib
```

**UI Alan Adları (Sharp Alarm):**
- Hacim: `amount_change`, `avg_last_amounts`, `shock_raw`, `shock_value`, `volume_multiplier`, `max_volume_cap`, `volume_contrib`
- Oran: `previous_odds`, `current_odds`, `drop_pct`, `odds_multiplier_base`, `odds_multiplier_bucket`, `odds_multiplier`, `odds_value`, `max_odds_cap`, `odds_contrib`
- Pay: `previous_share`, `current_share`, `share_diff`, `share_multiplier`, `share_value`, `max_share_cap`, `share_contrib`
- Skor: `sharp_score`

**UI Alan Adları (Diğer Alarmlar):**
- Insider: `hacim_sok`, `oran_dusus_pct`, `gelen_para`, `snapshot_details` vb.
- VolumeShock: `volume_shock_value`, `hours_to_kickoff`, `hacim_soku_min_saat`, `hacim_soku_min_esik` vb.
- Dropping: `level`, `drop_pct`, `home_team`, `away_team`, `fixture_date` vb.

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