# SmartXFlow - Final Supabase Yapisi

## Ozet

Bu dokuman SmartXFlow projesinin aktif olarak kullandigi minimal ve temiz Supabase semasini icerir.

## Aktif Tablolar (16 tablo)

### Alarm Tablolari (7 adet)
| Tablo Adi | Aciklama | Unique Constraint |
|-----------|----------|-------------------|
| `sharp_alarms` | Sharp Money alarmlari | home, away, market, selection |
| `insider_alarms` | Insider alarmlari | home, away, market, selection |
| `bigmoney_alarms` | Big Money alarmlari | home, away, market, selection |
| `volumeshock_alarms` | Volume Shock alarmlari | home, away, market, selection |
| `dropping_alarms` | Dropping Odds alarmlari | home, away, market, selection |
| `publicmove_alarms` | Public Move alarmlari | home, away, market, selection |
| `volume_leader_alarms` | Volume Leader alarmlari | home, away, market, old_leader, new_leader |

### Mac Veri Tablolari (8 adet)
| Tablo Adi | Aciklama |
|-----------|----------|
| `matches` | Mac bilgileri (home_team, away_team, league, match_date) |
| `odds_snapshots` | Oran snapshot'lari |
| `moneyway_1x2_history` | Moneyway 1X2 tarihce |
| `moneyway_ou25_history` | Moneyway O/U 2.5 tarihce |
| `moneyway_btts_history` | Moneyway BTTS tarihce |
| `dropping_1x2_history` | Dropping 1X2 tarihce |
| `dropping_ou25_history` | Dropping O/U 2.5 tarihce |
| `dropping_btts_history` | Dropping BTTS tarihce |

### Ayar Tablosu (1 adet)
| Tablo Adi | Aciklama |
|-----------|----------|
| `alarm_settings` | Alarm ayarlari (config JSON) |

## Kolon Detaylari

### sharp_alarms Kolonlari
- id, home, away, market, selection
- sharp_score, smart_score
- volume_contrib, odds_contrib, share_contrib
- volume, volume_shock_multiplier, amount_change
- opening_odds, previous_odds, current_odds, drop_percentage
- previous_share, current_share, share_change_percent
- weights (JSONB)
- match_date, event_time, trigger_at, created_at, alarm_type

### insider_alarms Kolonlari
- id, home, away, market, selection
- oran_dusus_pct, odds_change_percent
- gelen_para, hacim_sok, avg_volume_shock
- max_surrounding_hacim_sok, max_surrounding_incoming
- opening_odds, open_odds, current_odds
- surrounding_snapshots (JSONB), surrounding_count, snapshot_count
- drop_moment_index, drop_moment
- match_date, event_time, trigger_at, created_at, alarm_type

### bigmoney_alarms Kolonlari
- id, home, away, market, selection
- incoming_money, selection_total
- is_huge, huge_total
- match_date, event_time, trigger_at, created_at, alarm_type

### volumeshock_alarms Kolonlari
- id, home, away, market, selection
- volume_shock_value, multiplier
- incoming_money, new_money, avg_previous, avg_last_10
- hours_to_kickoff
- match_date, event_time, trigger_at, created_at, alarm_type

### dropping_alarms Kolonlari
- id, home, away, market, selection
- opening_odds, open_odds, current_odds
- drop_pct, drop_percentage, level
- match_date, event_time, trigger_at, created_at, alarm_type

### publicmove_alarms Kolonlari
- id, home, away, market, selection
- trap_score, volume, odds_drop
- share_before, share_after, share_change, delta
- match_date, event_time, trigger_at, created_at, alarm_type

### volume_leader_alarms Kolonlari
- id, home, away, market
- old_leader, old_leader_share
- new_leader, new_leader_share
- total_volume
- match_date, event_time, trigger_at, created_at, alarm_type

## Kullanilan SQL Dosyalari

1. **create_alarm_tables_v3.sql** - Minimal ve temiz sema (yeni kurulumlar icin)
2. **supabase_cleanup.sql** - Kullanilmayan yapilari tespit ve temizleme

## Temizlik Adimlari

1. Supabase Dashboard > SQL Editor'a gidin
2. `supabase_cleanup.sql` icindeki analiz sorgularini calistirin
3. "UNUSED - CAN DELETE" olarak isaretlenen tablolari silin
4. `create_alarm_tables_v3.sql` ile eksik tablolari/kolonlari ekleyin

## RLS ve Policy'ler

Tum tablolarda:
- RLS aktif
- "Allow all for X" policy'si tanimli
- Herkese okuma/yazma izni

## Indeksler

Tum alarm tablolari icin:
- `idx_X_home` - home kolonu
- `idx_X_created` - created_at kolonu

History tablolari icin:
- `idx_X_teams` - home, away kolonlari
