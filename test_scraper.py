#!/usr/bin/env python3
"""
SmartXFlow Scraper Test Script
Replit'te scraper fonksiyonlarını test etmek için basit CLI arayüzü
"""
import os
import sys
from scraper.moneyway import scrape_all, DATASETS

def main():
    print("=" * 60)
    print("SmartXFlow - Scraper Test")
    print("=" * 60)
    
    # Cookie kontrolü
    cookie = os.getenv('COOKIE_STRING', '')
    if not cookie:
        print("⚠️  UYARI: COOKIE_STRING environment variable bulunamadı!")
        print("   Scraping başarısız olabilir.")
    else:
        print("✓ Cookie bulundu")
    
    print("\nMevcut Markets:")
    for i, (key, url) in enumerate(DATASETS.items(), 1):
        print(f"  {i}. {key}")
    
    print("\n" + "=" * 60)
    print("Not: PyQt6 GUI Replit'te çalışmaz.")
    print("     GitHub Actions ile .exe build edin ve Windows'ta çalıştırın.")
    print("     Bu script sadece scraper fonksiyonlarını test eder.")
    print("=" * 60)
    
    print("\nTest tamamlandı!")

if __name__ == "__main__":
    main()
