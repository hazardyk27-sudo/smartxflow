# SmartXFlow – Odds & Volume Monitor

## Proje Özeti
Windows masaüstü uygulaması - arbworld.net'ten Moneyway ve Dropping Odds verilerini çekip, zaman serisi olarak saklayan ve grafiksel analiz sunan profesyonel bahis analiz aracı.

## Teknoloji Stack
- **Dil:** Python 3.11
- **UI Framework:** PyQt6 (Modern Qt6 tabanlı GUI)
- **Grafik:** Matplotlib (Zaman serisi grafikleri için)
- **Database:** SQLite (lokal) + Supabase (cloud)
- **Scraping:** BeautifulSoup4 + Requests (arbworld.net)
- **Build Tool:** PyInstaller (Windows .exe oluşturma için)
- **CI/CD:** GitHub Actions (otomatik .exe build)

## Proje Yapısı
```
.
├── yenversyon.py          # Ana PyQt6 GUI uygulaması (2369 satır)
├── yenversyon.spec        # PyInstaller build yapılandırması
├── scraper/              # Scraping modülü
│   ├── __init__.py
│   ├── moneyway.py       # 6 market için scraper (22KB)
│   └── core.py.old       # Eski dummy scraper (yedek)
├── core/                 # Çekirdek işlevsellik
│   ├── __init__.py
│   ├── storage.py        # SQLite + Supabase dual storage (9KB)
│   └── settings.py       # Ayarlar yönetimi
├── ui/                   # UI bileşenleri
│   ├── __init__.py
│   └── settings_dialog.py # Ayarlar diyalogu
├── data/                 # Scraped data (Git'e gitmez)
├── .github/
│   └── workflows/
│       └── build.yml     # GitHub Actions - PyQt6 .exe build
├── test_scraper.py       # Replit test script (CLI)
├── requirements.txt      # Python bağımlılıkları
├── settings.json         # Kullanıcı ayarları
├── .gitignore           # Git ignore kuralları
└── replit.md            # Bu dosya
```

## Özellikler

### Veri Toplama (6 Market)
1. **Moneyway Markets:**
   - 1-X-2 (Maç sonucu)
   - Over/Under 2.5 
   - BTTS (Both Teams To Score)
2. **Dropping Odds Markets:**
   - 1-X-2 (Maç sonucu)
   - Over/Under 2.5
   - BTTS

### Veritabanı & Zaman Serisi
- **Dual Storage:** SQLite (offline) + Supabase (cloud sync)
- **History Tracking:** Her scrape timestamp ile kaydedilir
- **Maç Bazlı Kayıt:** Her maç için ayrı geçmiş tutulur

### Grafik & Analiz
- **Matplotlib Integration:** Profesyonel zaman serisi grafikleri
- **Oran Hareketi:** Başlangıç → Güncel oran karşılaştırması (renkli ok göstergesi)
- **Para Akışı:** Moneyway yüzdesi ve miktarı takibi
- **İki Satırlı Hücre Gösterimi:** Oran + Yüzde/Miktar tek hücrede

### GUI Özellikleri (PyQt6)
- 6 market butonu (kolay geçiş)
- Tablo gösterimi (custom delegates)
- Maç seçimi ve detay görüntüleme
- Ayarlar diyalogu
- Dark theme

### GitHub Actions Workflow
- Her `main` branch push'unda otomatik olarak Windows .exe build edilir
- PyInstaller ile `yenversyon.spec` kullanılarak PyQt6 .exe oluşturulur
- Build edilen .exe, GitHub Actions "Artifacts" bölümünden 30 gün boyunca indirilebilir
- Tag push'larında otomatik Release oluşturulur

## Kullanım

### Geliştirme (Replit'te)
**Not:** PyQt6 GUI Replit'te çalışmaz (VNC gerektirir). Replit'te sadece scraper fonksiyonlarını test edebilirsiniz:

```bash
python test_scraper.py
```

### Tam Uygulama (Windows'ta)
GitHub Actions ile build edilen `.exe` dosyasını Windows'ta çalıştırın:
1. GitHub Actions "Artifacts" bölümünden `.exe`'yi indirin
2. Windows'ta çift tıklayın
3. Cookie bilgilerinizi ayarlara girin
4. 6 market butonuyla veri toplayın

### Scraper Geliştirme
1. `scraper/moneyway.py` dosyasını inceleyin
2. 6 farklı market için endpoint'ler tanımlı: `DATASETS` dict
3. Her market için özel extract fonksiyonu var
4. Cookie bilgisi `COOKIE_STRING` env var'ından okunur

### Windows .exe Build (GitHub Actions)
1. Kodunuzu GitHub'a push edin:
   ```bash
   git add .
   git commit -m "Update features"
   git push origin main
   ```
2. GitHub Actions otomatik olarak çalışacak
3. Actions sekmesinden "Build Windows EXE" workflow'unu açın
4. "Artifacts" bölümünden `SmartXFlow-Windows-EXE` dosyasını indirin

### Lokal .exe Build (Opsiyonel - Windows'ta)
```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller yenversyon.spec
```
.exe dosyası `dist/` klasöründe oluşturulacak.

## Sonraki Adımlar
1. Cookie bilgilerinizi güncelleyin (değiştiyse)
2. Supabase'de tabloları oluşturun (cloud sync için)
3. GitHub repo'nuza push yaparak otomatik .exe build'i test edin
4. Windows'ta .exe'yi çalıştırıp veri toplamayı test edin

## Notlar
- tkinter Python'un yerleşik kütüphanesi olduğundan ekstra kurulum gerektirmez
- Scraping kodları `scraper/` klasöründe modüler olarak organize edilmiştir
- Log penceresinde tüm işlemler zaman damgası ile kaydedilir
- Otomatik scraping arka planda çalışır, UI donmaz
- `.gitignore` ile Python ve build dosyaları versiyon kontrolünden hariç tutulmuştur

## Tarih
- **24 Kasım 2025:** Proje altyapısı oluşturuldu, temel GUI ve GitHub Actions hazırlandı
- **24 Kasım 2025:** ONEDIR mode + DLL packaging düzeltmesi tamamlandı
