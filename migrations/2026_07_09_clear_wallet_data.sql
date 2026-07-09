-- Tüm takip edilen cüzdan verilerini sıfırla (2026-07-09)
-- Supabase SQL Editor'da çalıştır, ardından Hetzner'de scraper'ı yeniden başlat.
DELETE FROM tracked_wallet_activity;
DELETE FROM tracked_wallet_redeems;
DELETE FROM tracked_wallet_positions;
