# SmartXFlow Monitor – Odds & Volume Tracker

### Overview
SmartXFlow Monitor is a professional betting odds tracking tool designed to scrape Moneyway and Dropping Odds data, store it as time series, and provide graphical analysis. The project aims for a zero-cost, 24/7 data collection and visualization solution through a hybrid architecture, minimizing reliance on Replit's free tier limitations. It functions as a pure data collection and visualization tool, with alarm calculations handled by a separate PC-based application and displayed on the web/desktop UI. The business vision is to provide a comprehensive, real-time data monitoring solution for betting markets with high market potential among professional bettors and analysts.

### User Preferences
- DEĞİŞİKLİK YAPMADAN ÖNCE SOR
- SADECE İSTENENİ YAP
- ANLAMADIĞINDA SOR
- KURALLARA UY
- DESKTOP UI'A DOKUNMA - Kullanıcı söyleyene kadar sadece mobil (@media max-width: 768px) değişiklik yap
- GITHUB KULLANICI ADI: hazardyk27-sudo
- UYGULAMA = desktop_app.py
- SCRAPER'A DOKUNMA
- SADECE "push et" DENDIGINDE
- SADECE UYGULAMA DOSYALARI
- PUSH KOMUTU: `git push --force` kullan
- DEBUG DOSYASI
- SUPABASE SECRET ADI - Her zaman SUPABASE_ANON_KEY kullan
- WEB URL: https://ea61a90d-fbe5-4a43-993a-4a7ea861590b-00-el7p3v8o3jsj.janeway.replit.dev/
- ALARM CALC STATUS KURALI: Her alarm türü için AYRI CalcStatus elementi olmalı:
  - Sharp: `calcStatus`, `calcProgress` elementleri + `showCalcStatus()`, `hideCalcStatus()` fonksiyonları
  - Insider: `insiderCalcStatus`, `insiderCalcProgress` elementleri + `showInsiderCalcStatus()`, `hideInsiderCalcStatus()` fonksiyonları
  - BigMoney: `bigMoneyCalcStatus`, `bigMoneyCalcProgress` elementleri + `showBigMoneyCalcStatus()`, `hideBigMoneyCalcStatus()` fonksiyonları
  - Yeni alarm eklendiğinde: `[alarmName]CalcStatus`, `[alarmName]CalcProgress` + `show[AlarmName]CalcStatus()`, `hide[AlarmName]CalcStatus()` oluştur

### System Architecture

**Core Architecture:**
The system uses a hybrid architecture with Supabase as the single source of truth for alarms. A standalone PC-based Python application (`SmartXFlow Admin Panel v1.04`) scrapes data and calculates alarms, writing them directly to Supabase. A Flask web application (Replit-based) reads and displays alarms, with scraping disabled. A PyInstaller-built desktop application provides a native UI by embedding a local Flask backend within a pywebview window.

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
- **Timezone:** All backend/DB timestamps are UTC; frontend displays in `Europe/Istanbul`.
- **Scrape Interval:** Fixed at 10 minutes.
- **Prematch System:** Only prematch data is tracked; no data for in-play or past matches (older than D-1).
- **Telegram Notifications:** Real-time alarm notifications via Telegram bot with:
    - Per-alarm-type enable/disable
    - BigMoney retrigger support (min delta + cooldown)
    - Deduplication via `telegram_sent_log` table
    - Rate limiting and retry handling
    - Visual card notifications (Playwright HTML-to-PNG) matching web UI design
    - Three-tier fallback: Playwright → Pillow → Text
    - Message mode setting in Admin Panel (image/text)
- **API Optimization:**
    - `/api/alarms/all`: Batch endpoint for 7 alarm types, with client-side caching (45s TTL).
    - `/api/match/<match_id>/snapshot`: Endpoint for all match-related data (alarms, metadata, moneyway, dropping_odds). Uses a 12-character MD5 `match_id`.
- **Supabase Request Optimization (2025-12-28):**
    - Server-side cache TTL: 60 saniye (alarm ve match verisi)
    - Tab Visibility: Arka plandaki tab'lar auto-refresh yapmaz
    - Jitter: 0-60 saniye random delay (synchronized spike önleme)
    - Baseline: 75k istek/gün → Hedef: ~25-30k istek/gün (%60-80 azalma)

**Data Model (Supabase Tables):**
- `fixtures`: Stores match metadata with a unique `match_id_hash`.
- `moneyway_snapshots`: Stores time-series moneyway data.
- `dropping_odds_snapshots`: Stores time-series dropping odds data.

**match_id_hash Contract:**
A critical, immutable contract defines `match_id_hash` as a 12-character MD5 hash of a canonical string: `league|home|away`. All components are normalized (trimmed, lowercase, single spaces, Turkish character normalization). **NOTE:** Kickoff/date is NOT used in hash calculation - this simplifies the system and prevents format-related hash mismatches.

**Endpoint Response Contract (`/api/match/<match_id_hash>/snapshot`):**
The API response structure for match snapshots is immutable, ensuring backward compatibility. It includes `metadata`, `alarms` (grouped by type), `moneyway`, `dropping_odds`, and `updated_at_utc`. New fields can be added, but existing field names, types, or the overall structure cannot be changed.

### External Dependencies
- **arbworld.net:** Primary data source for betting odds.
- **Supabase:** Cloud-based PostgreSQL used for all data storage.
- **GitHub Actions:** Used for continuous integration and deployment, specifically for automated .exe builds.

---

## 🔒 DEĞİŞMEYECEK SÖZLEŞMELER (Immutable Contracts)

> **UYARI:** Bu bölümdeki kurallar SABİTTİR. Değişiklik yapılmadan önce tüm sistemlerin (Scraper, Admin.exe, Backend) güncellenmesi gerekir.

### 1. match_id_hash Sözleşmesi

**Sabit Özellikler:**

| Özellik | Değer |
|---------|-------|
| Uzunluk | 12 karakter (sabit) |
| Algoritma | MD5 |
| Format | `league\|home\|away` |

**NOT:** Kickoff/date hash hesaplamasında KULLANILMIYOR - bu sistem basitleştirir ve format kaynaklı hash uyumsuzluklarını önler.

**Normalizasyon Pipeline (Adım Adım):**

```python
import hashlib
import re

def normalize_field(value: str) -> str:
    """
    Adım 1: String normalizasyonu
    Tüm sistemlerde (Scraper, Admin.exe, Backend) aynı mantık uygulanır.
    ÖNEMLİ: Türkçe karakter normalizasyonu LOWERCASE'DEN ÖNCE yapılmalı!
    """
    if not value:
        return ""
    # 1. Trim - baştaki/sondaki boşlukları sil
    value = value.strip()
    # 2. Türkçe karakter normalizasyonu (LOWERCASE'DEN ÖNCE!)
    # İ → I, ı → i (büyük harf İ lowercase önce I olmalı)
    value = value.replace('ı', 'i').replace('İ', 'I')
    # 3. Lowercase - küçük harfe çevir
    value = value.lower()
    # 4. Çoklu boşlukları tek boşluğa indir
    value = ' '.join(value.split())
    return value

def generate_match_id(home: str, away: str, league: str) -> str:
    """
    Hash üretimi - DEĞİŞMEYECEK HASH FONKSİYONU
    Tüm sistemlerde (Scraper, Admin.exe, Backend) bu kullanılır.
    
    NOT: Kickoff/date KULLANILMIYOR - sadece league, home, away
    """
    # Normalizasyon
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    
    # Canonical string: league|home|away (bu sıra SABİT)
    canonical = f"{league_norm}|{home_norm}|{away_norm}"
    
    # 12 karakterlik MD5 hash
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]
```

**Örnek:**
```
Girdi: 
  home = "Manchester UTD"
  away = "Arsenal"
  league = "Premier League"

Normalize:
  home = "manchester utd"
  away = "arsenal"
  league = "premier league"

Canonical: "premier league|manchester utd|arsenal"
Hash: "7e0c6e92b4ba" (12 karakter)
```

---

### 2. Veritabanı Şema Sözleşmesi

**fixtures Tablosu:**
```sql
CREATE TABLE fixtures (
  internal_id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12) NOT NULL UNIQUE,
  home_team VARCHAR(100) NOT NULL,
  away_team VARCHAR(100) NOT NULL,
  league VARCHAR(150) NOT NULL,
  kickoff_utc TIMESTAMP WITH TIME ZONE NOT NULL,
  fixture_date DATE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_fixtures_hash ON fixtures(match_id_hash);
CREATE INDEX idx_fixtures_date ON fixtures(fixture_date);
```

**moneyway_snapshots Tablosu:**
```sql
CREATE TABLE moneyway_snapshots (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
  market VARCHAR(10) NOT NULL,      -- '1X2', 'OU25', 'BTTS'
  selection VARCHAR(10) NOT NULL,   -- '1', 'X', '2', 'O', 'U', 'Y', 'N'
  odds DECIMAL(6,2),
  volume DECIMAL(12,2),
  share DECIMAL(5,2),
  scraped_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_mw_hash ON moneyway_snapshots(match_id_hash);
CREATE INDEX idx_mw_scraped ON moneyway_snapshots(scraped_at_utc);
```

**dropping_odds_snapshots Tablosu:**
```sql
CREATE TABLE dropping_odds_snapshots (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
  market VARCHAR(10) NOT NULL,
  selection VARCHAR(10) NOT NULL,
  opening_odds DECIMAL(6,2),
  current_odds DECIMAL(6,2),
  drop_pct DECIMAL(5,2),
  volume DECIMAL(12,2),
  scraped_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_do_hash ON dropping_odds_snapshots(match_id_hash);
CREATE INDEX idx_do_scraped ON dropping_odds_snapshots(scraped_at_utc);
```

**İlişki Kuralları:**
- fixtures (1) ←→ (N) moneyway_snapshots
- fixtures (1) ←→ (N) dropping_odds_snapshots
- Snapshot yazılmadan önce fixture kaydı mevcut olmalı

---

### 3. Health Check SQL'leri

```sql
-- 1. Duplicate hash kontrolü (ASLA olmamalı)
SELECT match_id_hash, COUNT(*) 
FROM fixtures GROUP BY match_id_hash HAVING COUNT(*) > 1;

-- 2a. Orphan moneyway snapshot'lar
SELECT s.id, s.match_id_hash 
FROM moneyway_snapshots s 
LEFT JOIN fixtures f ON f.match_id_hash = s.match_id_hash 
WHERE f.internal_id IS NULL;

-- 2b. Orphan dropping odds snapshot'lar
SELECT d.id, d.match_id_hash 
FROM dropping_odds_snapshots d 
LEFT JOIN fixtures f ON f.match_id_hash = d.match_id_hash 
WHERE f.internal_id IS NULL;

-- 3. Snapshot'sız fixture'lar
SELECT f.match_id_hash, f.home_team, f.away_team 
FROM fixtures f 
LEFT JOIN moneyway_snapshots s ON s.match_id_hash = f.match_id_hash 
WHERE s.id IS NULL;

-- 4. Stale fixture'lar (30 dk snapshot gelmemiş)
SELECT f.match_id_hash, MAX(s.scraped_at_utc) AS last_snapshot 
FROM fixtures f 
LEFT JOIN moneyway_snapshots s ON s.match_id_hash = f.match_id_hash 
GROUP BY f.match_id_hash 
HAVING MAX(s.scraped_at_utc) < NOW() - INTERVAL '30 minutes';
```

---

### 4. Endpoint Response Sözleşmesi

**Endpoint:** `/api/match/<match_id_hash>/snapshot`

**Response Contract (Değiştirilemez):**
```json
{
  "metadata": {
    "match_id": "string (12 char)",
    "internal_id": "number | null",
    "home": "string",
    "away": "string",
    "league": "string",
    "kickoff_utc": "string (ISO 8601)",
    "fixture_date": "string",
    "source": "string (cache | fixture_table | alarm_data)"
  },
  "alarms": {
    "sharp": [],
    "insider": [],
    "bigmoney": [],
    "volumeshock": [],
    "dropping": [],
    "publicmove": [],
    "volumeleader": []
  },
  "moneyway": "array | null",
  "dropping_odds": "array | null",
  "updated_at_utc": "string (ISO 8601)"
}
```

**Değişiklik Kuralları:**
| İzin Verilen ✅ | Yasak ❌ |
|----------------|----------|
| Yeni alan eklemek | Alan adını değiştirmek |
| Yeni nested object | Tipi değiştirmek |
| Array'e eleman | Yapıyı bozmak |

---

### 5. Phase 2 Uygulama Planı

1. Supabase'de fixtures, moneyway_snapshots, dropping_odds_snapshots oluştur
2. Admin.exe: generate_match_id() fonksiyonunu normalize et
3. RPC: get_full_match_snapshot(hash) fonksiyonu oluştur
4. Web endpoint: RPC sonuçlarını response contract'a maple