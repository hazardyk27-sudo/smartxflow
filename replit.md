# SmartXFlow – Odds & Volume Monitor

## Proje Ozeti
Windows masaustu uygulamasi - arbworld.net'ten Moneyway ve Dropping Odds verilerini cekip, zaman serisi olarak saklayan ve grafiksel analiz sunan profesyonel bahis analiz araci.

## Teknoloji Stack
- **Dil:** Python 3.11
- **UI Framework:** Tkinter (native Python GUI)
- **Grafik:** Matplotlib (Zaman serisi grafikleri)
- **Database:** SQLite (lokal) + Supabase (cloud - opsiyonel)
- **Scraping:** BeautifulSoup4 + Requests (arbworld.net)
- **Build Tool:** PyInstaller (Windows .exe)
- **CI/CD:** GitHub Actions (otomatik .exe build)

## Proje Yapisi
```
.
├── main.py               # Ana Tkinter GUI uygulamasi (550+ satir)
├── scraper/              # Scraping modulu
│   ├── __init__.py
│   ├── core.py           # Scraper bridge (run_scraper fonksiyonu)
│   └── moneyway.py       # 6 market icin scraper (566 satir)
├── services/             # Servis katmani
│   ├── __init__.py
│   └── supabase_client.py # Supabase + SQLite client
├── core/                 # Cekirdek islevsellik
│   ├── __init__.py
│   └── storage.py        # SQLite + Supabase dual storage
├── data/                 # Scraped data (Git'e gitmez)
├── .github/
│   └── workflows/
│       └── build.yml     # GitHub Actions - Windows .exe build
├── embedded_config.py    # Gomulu yapilandirma
├── requirements.txt      # Python bagimliliklari
└── replit.md            # Bu dosya
```

## Ozellikler

### Veri Toplama (6 Market)
1. **Moneyway Markets:**
   - 1-X-2 (Mac sonucu)
   - Over/Under 2.5 
   - BTTS (Both Teams To Score)
2. **Dropping Odds Markets:**
   - 1-X-2 (Mac sonucu)
   - Over/Under 2.5
   - BTTS

### Iki Sekmeli GUI
1. **Kontrol Paneli:**
   - "Simdi Scrape Et" butonu
   - Otomatik scrape (1-30 dakika aralik)
   - Renkli durum gostergesi (yesil/kirmizi)
   - Dark theme log penceresi

2. **Veri & Grafik:**
   - 6 market radio button secimi
   - Mac listesi (SQLite'dan)
   - Matplotlib zaman serisi grafigi
   - Oran degisimi gorselestirme

### Veritabani & Zaman Serisi
- **Dual Storage:** SQLite (offline) + Supabase (cloud sync - opsiyonel)
- **History Tracking:** Her scrape timestamp ile kaydedilir
- **Mac Bazli Kayit:** Her mac icin ayri gecmis tutulur

### GitHub Actions Workflow
- Her `main` branch push'unda otomatik olarak Windows .exe build edilir
- PyInstaller ile tek dosya .exe olusturulur
- Build edilen .exe, GitHub Actions "Artifacts" bolumunden 30 gun boyunca indirilebilir

## Kullanim

### Windows'ta
1. GitHub Actions "Artifacts" bolumunden `SmartXFlow-Windows-EXE.zip` indir
2. Zip'i ac → `SmartXFlow.exe` cift tikla
3. "Simdi Scrape Et" ile veri cek
4. "Veri & Grafik" sekmesinde maclari incele

### Supabase Kurulumu (Opsiyonel)
Cloud sync icin:
1. supabase.com'da proje olustur
2. SQL Editor'de asagidaki tablolari olustur:

```sql
CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    external_match_id TEXT,
    league TEXT,
    home_team TEXT,
    away_team TEXT,
    start_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE market_snapshots (
    id SERIAL PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    source TEXT,
    market TEXT,
    selection TEXT,
    odds NUMERIC,
    money_percent NUMERIC,
    volume NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);
```

3. Environment variable olarak ayarla:
   - SUPABASE_URL
   - SUPABASE_ANON_KEY

## Teknik Notlar
- **Database:** data/moneyway.db (LocalDatabase class in services/supabase_client.py)
- **Trend Arrows:** Sadece Dropping Odds marketlerinde görünür (↑/↓ yeşil/kırmızı)
- **Trend Functions:** `getDirectTrendArrow` (API trend) + `getTableTrendArrow` (prev/curr hesaplama)
- **PNG Export:** html2canvas ile tüm modal sayfası (bilgiler + grafik) indirilir
- **Volume Format:** £ sembolü + binlik ayraç (£32,218 formatında)
- **Grafik Ölçekleme:** 5dk/10dk/30dk/1saat/6saat/12saat/1gün bucket aralıkları (veri filtrelemez, sadece ölçekler)

## Son Guncellemeler
- **25 Kasim 2025:** PNG export - tüm modal sayfası indirilir (html2canvas)
- **25 Kasim 2025:** Volume £ sembolü ve binlik ayraç formatı eklendi
- **25 Kasim 2025:** Grafik zaman filtresi: veri filtrelemek yerine bucket ölçekleme
- **25 Kasim 2025:** Grafik noktaları küçültüldü (pointRadius: 3)
- **25 Kasim 2025:** Modal odds/details uyumsuzluğu düzeltildi
- **25 Kasim 2025:** BTTS Drop market trend okları düzeltildi
- **24 Kasim 2025:** Flask Web UI + GitHub Dark tema
- **24 Kasim 2025:** Chart.js grafik entegrasyonu
- **24 Kasim 2025:** Build basariyla tamamlandi
