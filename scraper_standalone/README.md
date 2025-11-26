# SmartXFlowScraper - Standalone Veri Toplayici

PC'de calisan bagimsiz scraper. arbworld.net'ten veri cekip Supabase'e yazar.

## Kurulum

### Adim 1: Zip'i Indir
GitHub Actions'tan `SmartXFlowScraper-Windows-EXE.zip` indir.

### Adim 2: Zip'i Ac
Herhangi bir klasore zip'i ac. Icinde 3 dosya olacak:
- `SmartXFlowScraper.exe` - Ana program
- `config.json` - Ayarlar dosyasi
- `README.txt` - Bu talimatlar

### Adim 3: config.json Duzenle
`config.json` dosyasini Notepad ile ac ve su degerleri gir:

```json
{
    "SUPABASE_URL": "https://PROJE_ID.supabase.co",
    "SUPABASE_ANON_KEY": "eyJ..."
}
```

**Bu degerleri nereden bulurum?**
1. supabase.com'a git
2. Projeni sec
3. Settings > API bolumune git
4. URL: Project URL kisminda
5. anon key: Project API Keys > anon public kisminda

### Adim 4: Calistir
`SmartXFlowScraper.exe` uzerine cift tikla.

Konsol penceresi acilacak ve su mesajlari goreceksin:
```
==================================================
  SmartXFlow Standalone Scraper v1.0.0
  PC'de calisan bagimsiz veri toplayici
==================================================

[HH:MM] Config yuklendi: config.json
[HH:MM] Supabase baglantisi hazir
[HH:MM] Scrape araligi: 10 dakika
--------------------------------------------------
[HH:MM] Scrape basladi...
[HH:MM]   moneyway-1x2 cekiliyor...
[HH:MM]   moneyway-1x2: 45 satir yazildi
...
[HH:MM] Scrape tamamlandi - Toplam: 285 satir
[HH:MM] 10 dakika bekleniyor...
```

### Adim 5: Pencereyi Kapatma!
Program arkaplanda calismali. Pencereyi minimize edebilirsin ama KAPATMA.

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

- Scrape araligi: 10 dakika (sabit)
- Turkiye saati (Europe/Istanbul) kullanir
- 6 market izlenir:
  - Moneyway 1X2
  - Moneyway Over/Under 2.5
  - Moneyway BTTS
  - Dropping Odds 1X2
  - Dropping Odds Over/Under 2.5
  - Dropping Odds BTTS

## Supabase Tablo Yapisi

Asagidaki tablolarin Supabase'te olusturulmasi gerekir:

```sql
-- Ana tablolar (guncel veri)
CREATE TABLE moneyway_1x2 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Odds1 TEXT, OddsX TEXT, Odds2 TEXT, Pct1 TEXT, Amt1 TEXT, PctX TEXT, AmtX TEXT, Pct2 TEXT, Amt2 TEXT, Volume TEXT);
CREATE TABLE moneyway_ou25 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Under TEXT, Line TEXT, Over TEXT, PctUnder TEXT, AmtUnder TEXT, PctOver TEXT, AmtOver TEXT, Volume TEXT);
CREATE TABLE moneyway_btts (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Yes TEXT, No TEXT, PctYes TEXT, AmtYes TEXT, PctNo TEXT, AmtNo TEXT, Volume TEXT);
CREATE TABLE dropping_1x2 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Odds1 TEXT, Odds1_prev TEXT, OddsX TEXT, OddsX_prev TEXT, Odds2 TEXT, Odds2_prev TEXT, Trend1 TEXT, TrendX TEXT, Trend2 TEXT, Volume TEXT);
CREATE TABLE dropping_ou25 (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, Under TEXT, Under_prev TEXT, Line TEXT, Over TEXT, Over_prev TEXT, TrendUnder TEXT, TrendOver TEXT, PctUnder TEXT, AmtUnder TEXT, PctOver TEXT, AmtOver TEXT, Volume TEXT);
CREATE TABLE dropping_btts (ID TEXT, League TEXT, Date TEXT, Home TEXT, Away TEXT, OddsYes TEXT, OddsYes_prev TEXT, OddsNo TEXT, OddsNo_prev TEXT, TrendYes TEXT, TrendNo TEXT, PctYes TEXT, AmtYes TEXT, PctNo TEXT, AmtNo TEXT, Volume TEXT);

-- Gecmis tablolari (her scrape'te yeni satirlar eklenir)
CREATE TABLE moneyway_1x2_history (LIKE moneyway_1x2 INCLUDING ALL, ScrapedAt TEXT);
CREATE TABLE moneyway_ou25_history (LIKE moneyway_ou25 INCLUDING ALL, ScrapedAt TEXT);
CREATE TABLE moneyway_btts_history (LIKE moneyway_btts INCLUDING ALL, ScrapedAt TEXT);
CREATE TABLE dropping_1x2_history (LIKE dropping_1x2 INCLUDING ALL, ScrapedAt TEXT);
CREATE TABLE dropping_ou25_history (LIKE dropping_ou25 INCLUDING ALL, ScrapedAt TEXT);
CREATE TABLE dropping_btts_history (LIKE dropping_btts INCLUDING ALL, ScrapedAt TEXT);
```
