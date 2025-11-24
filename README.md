# SmartXFlow – Odds & Volume Monitor

Windows masaüstü uygulaması - Odds ve Volume verilerini izleme ve scraping için Python/tkinter tabanlı GUI uygulaması.

## Özellikler

- ✅ **Manuel Scraping:** "Şimdi Scrape Et" butonu ile anında veri çekme
- ✅ **Otomatik Scraping:** Belirlenen aralıklarla (1, 5, 10, 15, 30 dakika) otomatik veri toplama
- ✅ **Canlı Log Penceresi:** Tüm işlemlerin zaman damgalı kaydı
- ✅ **Thread-Safe:** UI donmaması için arka plan işleme, güvenli thread yönetimi
- ✅ **GitHub Actions:** Her push'ta otomatik Windows .exe build
- ✅ **Modüler Yapı:** Scraper kodlarını kolayca ekleme/güncelleme

## Kurulum

### Geliştirme Ortamı

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# Uygulamayı çalıştır
python main.py
```

### Windows .exe İndirme

Her kod push'unda GitHub Actions otomatik olarak Windows .exe dosyası oluşturur:

1. GitHub repo'nun **Actions** sekmesine gidin
2. En son **Build Windows EXE** workflow'unu açın
3. **Artifacts** bölümünden `SmartXFlow-Windows-EXE` dosyasını indirin
4. İndirdiğiniz .exe dosyasını çalıştırın

## Kullanım

### 1. Manuel Scraping
- "Şimdi Scrape Et" butonuna tıklayın
- Scraping işlemi arka planda çalışır
- Sonuçlar log penceresinde görüntülenir

### 2. Otomatik Scraping
- Aralık dropdown'ından süre seçin (1-30 dakika)
- "Otomatik Scrape Başlat" butonuna tıklayın
- İşlemi durdurmak için "Durdur" butonuna tıklayın

### 3. Log Yönetimi
- Tüm işlemler otomatik olarak log penceresine kaydedilir
- "Log'u Temizle" butonu ile log geçmişini silebilirsiniz

## Scraper Kodlarını Ekleme

Kendi scraping mantığınızı eklemek için:

1. `scraper/core.py` dosyasını açın
2. `run_scraper()` fonksiyonunu düzenleyin:

```python
def run_scraper():
    """
    Ana scraping fonksiyonu
    """
    # Buraya kendi scraping kodunuzu ekleyin
    # Örnek: API çağrıları, web scraping, veri işleme vb.
    
    # Veri çek
    data = your_scraping_logic()
    
    # Sonuç döndür
    return f"Toplam {len(data)} kayıt çekildi"
```

3. Ek Python kütüphaneleri gerekiyorsa `requirements.txt`'ye ekleyin:

```bash
pip install yeni-paket
pip freeze > requirements.txt
```

## Proje Yapısı

```
SmartXFlow/
├── main.py                 # Ana uygulama (tkinter GUI)
├── scraper/               # Scraping modülü
│   ├── __init__.py
│   └── core.py           # Scraping fonksiyonları
├── config/               # Yapılandırma dosyaları için
├── .github/
│   └── workflows/
│       └── build.yml     # GitHub Actions - otomatik .exe build
├── requirements.txt      # Python bağımlılıkları
├── .gitignore           # Git ignore kuralları
└── README.md            # Bu dosya
```

## GitHub Actions Workflow

`.github/workflows/build.yml` dosyası her `main` branch push'unda:

1. Windows runner üzerinde Python 3.11 kurar
2. Bağımlılıkları yükler (`requirements.txt`)
3. PyInstaller ile tek dosya .exe oluşturur (`--onefile --noconsole`)
4. Oluşturulan .exe'yi Artifacts olarak yükler (30 gün saklanır)
5. Tag push'larında otomatik Release oluşturur

### Workflow'u Manuel Tetikleme

GitHub repo'nuzda:
1. **Actions** sekmesine gidin
2. **Build Windows EXE** workflow'unu seçin
3. **Run workflow** butonuna tıklayın

## Teknik Detaylar

### Thread Safety
- UI güncellemeleri queue sistemi ile ana thread'de yapılır
- Arka plan scraping işlemleri için ayrı thread'ler kullanılır
- Thread lifecycle doğru yönetilir (join ile bekleme)
- Race condition'lar önlenir

### UI Özellikleri
- **Framework:** tkinter (Python built-in)
- **Responsive:** Thread kullanımı ile UI donması yok
- **Log System:** ScrolledText widget ile otomatik kaydırma
- **Buton Yönetimi:** Duruma göre aktif/pasif buton kontrolü

### .exe Build
- **Tool:** PyInstaller 6.3.0
- **Parametreler:** `--onefile --noconsole`
- **Çıktı:** Tek dosya .exe (konsol penceresi yok)

## Sık Sorulan Sorular

**S: .exe dosyası nerede?**
GitHub Actions → Build Windows EXE → Artifacts bölümünden indirin.

**S: Scraping kodlarımı nasıl eklerim?**
`scraper/core.py` dosyasındaki `run_scraper()` fonksiyonunu düzenleyin.

**S: Uygulama neden donuyor?**
Thread-safe implementasyon sayesinde UI donması olmamalı. Eğer yaşanıyorsa, scraping kodunuzun hata verip vermediğini kontrol edin.

**S: GitHub Actions çalışmıyor?**
Repo ayarlarınızda Actions'ın etkin olduğundan emin olun.

## Lisans

Bu proje açık kaynak olarak geliştirilmiştir.

## Destek

Sorunlar için GitHub Issues kullanabilirsiniz.
