"""
Core scraper fonksiyonları - arbworld.net Moneyway & Odds
"""

import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import json


def run_scraper():
    """
    Ana scraping fonksiyonu - arbworld.net'ten moneyway/odds verilerini çeker
    
    Returns:
        str: Scraping sonucu mesajı
    """
    try:
        # Cookie'yi environment variable'dan al (güvenlik için)
        cookies_str = os.getenv('ARBWORLD_COOKIES', '')
        
        if not cookies_str:
            return "HATA: Cookie bilgisi bulunamadı! Environment variable'ı ekleyin."
        
        # URL
        url = "https://arbworld.net/en/moneyway/football-1-x-2"
        
        # Headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
        
        # Cookie'leri parse et
        cookies = parse_cookies(cookies_str)
        
        # Session oluştur
        session = requests.Session()
        session.headers.update(headers)
        session.cookies.update(cookies)
        
        # İstek gönder
        print(f"[{datetime.now().strftime('%H:%M:%S')}] arbworld.net'e bağlanılıyor...")
        response = session.get(url, timeout=30)
        
        if response.status_code != 200:
            return f"HATA: HTTP {response.status_code} - Bağlantı başarısız"
        
        # HTML parse et
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Veri çıkar
        matches_data = extract_moneyway_data(soup)
        
        if not matches_data:
            return "UYARI: Veri bulunamadı. Sayfa yapısı değişmiş olabilir."
        
        # Veriyi kaydet (opsiyonel)
        save_data(matches_data)
        
        return f"✓ Başarılı! {len(matches_data)} maç verisi çekildi. Son güncelleme: {datetime.now().strftime('%H:%M:%S')}"
        
    except requests.Timeout:
        return "HATA: Bağlantı zaman aşımına uğradı"
    except requests.ConnectionError:
        return "HATA: İnternet bağlantısı yok"
    except Exception as e:
        return f"HATA: {str(e)}"


def parse_cookies(cookie_string):
    """
    Cookie string'ini dictionary'e çevir
    
    Args:
        cookie_string: Cookie string (örn: "key1=value1; key2=value2")
    
    Returns:
        dict: Cookie dictionary
    """
    cookies = {}
    if cookie_string:
        for item in cookie_string.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key.strip()] = value.strip()
    return cookies


def extract_moneyway_data(soup):
    """
    HTML'den moneyway/odds verilerini çıkar
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        list: Maç verileri listesi
    """
    matches = []
    
    # Tablo satırlarını bul (sayfa yapısına göre ayarlanmalı)
    # Bu örnek yapı - gerçek yapıya göre güncellenmelidir
    
    # Örnek: match row'ları bul
    rows = soup.find_all('tr', class_='match-row') or soup.find_all('tr')
    
    for row in rows:
        try:
            # Maç bilgilerini çıkar (örnek)
            cells = row.find_all('td')
            
            if len(cells) >= 5:  # Minimum hücre sayısı
                match_info = {
                    'timestamp': datetime.now().isoformat(),
                    'teams': cells[0].get_text(strip=True) if cells else 'N/A',
                    'league': cells[1].get_text(strip=True) if len(cells) > 1 else 'N/A',
                    'odds_home': cells[2].get_text(strip=True) if len(cells) > 2 else 'N/A',
                    'odds_draw': cells[3].get_text(strip=True) if len(cells) > 3 else 'N/A',
                    'odds_away': cells[4].get_text(strip=True) if len(cells) > 4 else 'N/A',
                }
                matches.append(match_info)
        except Exception as e:
            print(f"Satır parse hatası: {e}")
            continue
    
    return matches


def save_data(data, filename='data/moneyway_data.json'):
    """
    Veriyi JSON dosyasına kaydet
    
    Args:
        data: Kaydedilecek veri
        filename: Dosya adı
    """
    try:
        # data klasörü yoksa oluştur
        os.makedirs('data', exist_ok=True)
        
        # Mevcut veriyi oku
        existing_data = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        
        # Yeni veriyi ekle
        existing_data.extend(data)
        
        # Kaydet
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        print(f"Veri kaydedildi: {filename}")
    except Exception as e:
        print(f"Kaydetme hatası: {e}")


# Ek yardımcı fonksiyonlar
def scrape_odds():
    """Sadece odds verilerini çek"""
    return run_scraper()


def scrape_volume():
    """Sadece volume verilerini çek"""
    return run_scraper()
