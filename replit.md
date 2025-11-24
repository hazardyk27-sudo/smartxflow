# SmartXFlow – Odds & Volume Monitor

## Proje Özeti
Windows masaüstü uygulaması - Odds ve Volume verilerini izleme ve scraping için Python/tkinter tabanlı GUI uygulaması.

## Teknoloji Stack
- **Dil:** Python 3.11
- **UI Framework:** tkinter (Python'un yerleşik GUI kütüphanesi)
- **Build Tool:** PyInstaller (Windows .exe oluşturma için)
- **CI/CD:** GitHub Actions (otomatik .exe build)

## Proje Yapısı
```
.
├── main.py                 # Ana uygulama giriş noktası (tkinter GUI)
├── scraper/               # Scraping modülü
│   ├── __init__.py
│   └── core.py           # Scraping fonksiyonları (şu an dummy)
├── config/               # Yapılandırma dosyaları için
├── .github/
│   └── workflows/
│       └── build.yml     # GitHub Actions - otomatik .exe build
├── requirements.txt      # Python bağımlılıkları
├── .gitignore           # Git ignore kuralları
└── replit.md            # Bu dosya
```

## Özellikler

### Mevcut Özellikler
1. **Manuel Scrape:** "Şimdi Scrape Et" butonu ile anında scraping
2. **Otomatik Scrape:** Belirlenen aralıklarla (1, 5, 10, 15, 30 dakika) otomatik scraping
3. **Durdur Butonu:** Otomatik scraping'i temiz bir şekilde durdurma
4. **Log Penceresi:** Tüm işlemlerin zaman damgalı kaydı
5. **Threading:** UI donmasını önlemek için arka plan thread'leri
6. **Temiz Kapanma:** Uygulama kapatılırken thread'lerin düzgün sonlanması

### GitHub Actions Workflow
- Her `main` branch push'unda otomatik olarak Windows .exe build edilir
- PyInstaller ile `--onefile --noconsole` parametreleriyle tek dosya .exe oluşturulur
- Build edilen .exe, GitHub Actions "Artifacts" bölümünden 30 gün boyunca indirilebilir
- Tag push'larında otomatik Release oluşturulur

## Kullanım

### Geliştirme (Replit'te)
```bash
python main.py
```

### Scraper Fonksiyonlarını Ekleme
1. `scraper/core.py` dosyasını açın
2. `run_scraper()` fonksiyonunu kendi scraping mantığınızla değiştirin
3. Ek modüller gerekiyorsa `requirements.txt`'ye ekleyin

### Windows .exe Build (GitHub Actions)
1. Kodunuzu GitHub'a push edin:
   ```bash
   git add .
   git commit -m "Update scraper"
   git push origin main
   ```
2. GitHub Actions otomatik olarak çalışacak
3. Actions sekmesinden "Build Windows EXE" workflow'unu açın
4. "Artifacts" bölümünden `SmartXFlow-Windows-EXE` dosyasını indirin

### Lokal .exe Build (Opsiyonel)
```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --noconsole --name SmartXFlow main.py
```
.exe dosyası `dist/` klasöründe oluşturulacak.

## Sonraki Adımlar
1. `scraper/core.py` içindeki dummy fonksiyonu gerçek scraping kodu ile değiştirin
2. Gerekli Python kütüphanelerini `requirements.txt`'ye ekleyin
3. İhtiyaç halinde `config/` klasörüne yapılandırma dosyaları ekleyin
4. GitHub repo'nuza push yaparak otomatik .exe build'i test edin

## Notlar
- tkinter Python'un yerleşik kütüphanesi olduğundan ekstra kurulum gerektirmez
- Scraping kodları `scraper/` klasöründe modüler olarak organize edilmiştir
- Log penceresinde tüm işlemler zaman damgası ile kaydedilir
- Otomatik scraping arka planda çalışır, UI donmaz
- `.gitignore` ile Python ve build dosyaları versiyon kontrolünden hariç tutulmuştur

## Tarih
- **24 Kasım 2025:** Proje altyapısı oluşturuldu, temel GUI ve GitHub Actions hazırlandı
