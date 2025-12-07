# SmartXFlowScraper - Standalone Veri Toplayici + Admin Panel

PC'de calisan bagimsiz scraper. arbworld.net'ten veri cekip Supabase'e yazar.
Alarm hesaplama ozelligi dahil.

## v1.02 Yenilikler
- **Admin Panel**: GUI ile scraper kontrolu
- **Scrape Araligi Ayari**: 1-60 dakika arasi ayarlanabilir
- **Konsol Penceresi**: Ayri pencerede log takibi
- **Alarm Hesaplama**: 7 alarm tipi otomatik hesaplanir

## Kurulum

### Adim 1: Zip'i Indir
GitHub Actions'tan `SmartXFlowScraper-Windows-EXE.zip` indir.

### Adim 2: Zip'i Ac
Herhangi bir klasore zip'i ac. Icinde su dosyalar olacak:
- `SmartXFlowAdmin.exe` - Admin Panel (ANA PROGRAM)
- `config.json` - Ayarlar dosyasi
- `README.txt` - Bu talimatlar

### Adim 3: config.json Duzenle (Opsiyonel)
`config.json` dosyasini Notepad ile ac ve su degerleri gir:

```json
{
    "SUPABASE_URL": "https://PROJE_ID.supabase.co",
    "SUPABASE_ANON_KEY": "eyJ...",
    "SCRAPE_INTERVAL_MINUTES": 10
}
```

**Not:** Bu ayarlari Admin Panel icinden de yapabilirsiniz.

**Bu degerleri nereden bulurum?**
1. supabase.com'a git
2. Projeni sec
3. Settings > API bolumune git
4. URL: Project URL kisminda
5. anon key: Project API Keys > anon public kisminda

### Adim 4: Calistir
`SmartXFlowAdmin.exe` uzerine cift tikla.

Admin Panel acilacak:
- Supabase ayarlarini gir
- Scrape araligini ayarla (1-60 dakika)
- "Baslat" butonuna tikla
- Konsol penceresi otomatik acilir

## Admin Panel Ozellikleri

### Ana Pencere
- **Supabase Ayarlari**: URL ve Key girisi
- **Scrape Ayarlari**: Scrape araligi (dakika)
- **Durum**: Scraper durumu, son scrape zamani, toplam scrape sayisi
- **Kontroller**: Baslat, Duraklat, Durdur butonlari
- **Manuel Alarm Hesapla**: Anlık alarm hesaplama

### Konsol Penceresi
- Tum scraper loglarini gosterir
- Yeşil metin, karanlık tema
- Otomatik scroll

## Alarm Tipleri

Scraper su alarm tiplerini otomatik hesaplar:
1. **Sharp Move**: Akilli para hareketi
2. **Insider Info**: Içeriden bilgi şüphesi
3. **Big Money / Huge Money**: Büyük para girişi
4. **Volume Shock**: Hacim şoku
5. **Dropping Odds**: Düşen oranlar (L1/L2/L3)
6. **Public Move**: Halk hareketi
7. **Volume Leader**: Lider değişimi

## SSS (Sik Sorulan Sorular)

### Program hata veriyor?
- `config.json` dosyasinin exe ile ayni klasorde oldugundan emin ol
- Supabase URL ve Key'in dogru oldugunu kontrol et
- Internet baglantini kontrol et

### Veri Replit'te gorunmuyor?
- Supabase tablolarinin dogru olusturuldugundan emin ol
- Replit'te de ayni Supabase URL ve Key kullanildigindan emin ol

### Bilgisayarimi kapatinca ne olur?
- Scraper durur, bilgisayari acinca tekrar calistir

## Teknik Bilgiler

- Varsayilan scrape araligi: 10 dakika (ayarlanabilir)
- Turkiye saati (Europe/Istanbul) kullanir
- 6 market izlenir:
  - Moneyway 1X2
  - Moneyway Over/Under 2.5
  - Moneyway BTTS
  - Dropping Odds 1X2
  - Dropping Odds Over/Under 2.5
  - Dropping Odds BTTS

## Dosya Yapisi

```
SmartXFlowScraper/
├── scraper_admin.py      # Admin Panel GUI
├── standalone_scraper.py # Scraper motoru
├── alarm_calculator.py   # Alarm hesaplama modulu
├── config.json           # Ayarlar
└── requirements.txt      # Python bagimliliklari
```

## Gelistirici Notlari

### Kaynak Koddan Calistirma
```bash
cd scraper_standalone
pip install -r requirements.txt
python scraper_admin.py
```

### EXE Olusturma
```bash
pyinstaller --onefile --windowed --name SmartXFlowAdmin scraper_admin.py
```
