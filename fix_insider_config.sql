-- Insider config'i düzelt - gereksiz min_volume alanlarını kaldır
-- Supabase SQL Editor'de çalıştır

UPDATE alarm_settings 
SET config = '{"hacim_sok_esigi": 0.1, "oran_dusus_esigi": 5, "max_para": 100, "max_odds_esigi": 1.9, "sure_dakika": 7}',
    updated_at = now()
WHERE alarm_type = 'insider';

SELECT * FROM alarm_settings WHERE alarm_type = 'insider';
