-- =============================================
-- ALARM_SETTINGS TABLOSU - Supabase SQL Editor'de çalıştır
-- =============================================

-- 1. Tablo oluştur
CREATE TABLE IF NOT EXISTS alarm_settings (
  alarm_type TEXT PRIMARY KEY,
  enabled BOOLEAN DEFAULT true,
  config JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. RLS aktif et
ALTER TABLE alarm_settings ENABLE ROW LEVEL SECURITY;

-- 3. Anon erişim policy'leri
CREATE POLICY "Allow anon select on alarm_settings" ON alarm_settings
  FOR SELECT TO anon USING (true);

CREATE POLICY "Allow anon insert on alarm_settings" ON alarm_settings
  FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "Allow anon update on alarm_settings" ON alarm_settings
  FOR UPDATE TO anon USING (true) WITH CHECK (true);

CREATE POLICY "Allow anon delete on alarm_settings" ON alarm_settings
  FOR DELETE TO anon USING (true);

-- 4. Başlangıç verileri (opsiyonel)
INSERT INTO alarm_settings (alarm_type, enabled, config) VALUES
('sharp', true, '{"min_volume_1x2": 3000, "min_volume_ou25": 1000, "min_volume_btts": 1000, "volume_multiplier": 5, "odds_multiplier": 8, "share_multiplier": 2, "min_sharp_score": 100, "min_amount_change": 1999}'),
('insider', true, '{"hacim_sok_esigi": 0.1, "oran_dusus_esigi": 5, "max_para": 100, "max_odds_esigi": 1.9, "sure_dakika": 7}'),
('bigmoney', true, '{"big_money_limit": 15000}'),
('volumeshock', true, '{"hacim_soku_min_saat": 3, "hacim_soku_min_esik": 5, "volume_shock_multiplier": 5.0, "min_volume_1x2": 1000, "min_volume_ou25": 500, "min_volume_btts": 300}'),
('dropping', true, '{"min_drop_l1": 10, "max_drop_l1": 17, "min_drop_l2": 17, "max_drop_l2": 20, "min_drop_l3": 20, "persistence_minutes": 120}'),
('publicmove', true, '{"min_volume_1x2": 3000, "min_volume_ou25": 1000, "min_volume_btts": 500, "min_sharp_score": 70}'),
('volumeleader', true, '{"min_volume_1x2": 2000, "min_volume_ou25": 1000, "min_volume_btts": 700, "leader_threshold": 50}')
ON CONFLICT (alarm_type) DO UPDATE SET config = EXCLUDED.config, updated_at = now();

SELECT 'alarm_settings tablosu başarıyla oluşturuldu!' as result;
