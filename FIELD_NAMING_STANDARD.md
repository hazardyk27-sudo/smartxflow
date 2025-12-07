# SmartXFlow Field Naming Standard V1.0

Bu dokuman tum sistemde kullanilacak tek canonical isim setini tanimlar.

## CANONICAL ISIM SOZLUGU

### 1. Para/Hacim Degisimi (Money/Volume Change)
| Kavram | CANONICAL ISIM | Eski/Yanlis Isimler (KALDIRILACAK) |
|--------|----------------|-----------------------------------|
| Gelen para miktari | `incoming_money` | amount_change, delta_amount, money_change, stake_diff, gelen_para, new_money |
| Onceki hacim | `previous_amount` | old_amount, prev_amount, amount_before |
| Guncel hacim | `current_amount` | new_amount, amount_after |
| Minimum para esigi | `min_incoming_money` | min_amount_change, min_stake |

### 2. Oran Degisimi (Odds Change)
| Kavram | CANONICAL ISIM | Eski/Yanlis Isimler (KALDIRILACAK) |
|--------|----------------|-----------------------------------|
| Oran dusus yuzdesi | `odds_drop_pct` | odds_change, odds_delta, drop_pct, drop_percentage, oran_dusus_pct, odds_change_percent |
| Acilis orani | `opening_odds` | open_odds, first_odds |
| Onceki oran | `previous_odds` | prev_odds, old_odds, odds_before |
| Guncel oran | `current_odds` | new_odds, last_odds, odds_after |
| Minimum dusus esigi | `min_odds_drop_pct` | min_drop, oran_dusus_esigi, insider_oran_dusus_esigi |

### 3. Pay/Yuzdelik Degisim (Share/Percentage Change)
| Kavram | CANONICAL ISIM | Eski/Yanlis Isimler (KALDIRILACAK) |
|--------|----------------|-----------------------------------|
| Pay degisimi | `share_change` | share_diff, percentage_change, market_share_delta, delta, share_change_percent |
| Onceki pay | `previous_share` | prev_share, old_share, share_before |
| Guncel pay | `current_share` | new_share, share_after |

### 4. Hacim Soku (Volume Shock)
| Kavram | CANONICAL ISIM | Eski/Yanlis Isimler (KALDIRILACAK) |
|--------|----------------|-----------------------------------|
| Sok degeri | `volume_shock` | hacim_sok, shock_value, shock_raw, volume_shock_value |
| Sok carpani | `volume_shock_multiplier` | multiplier, shock_mult |
| Onceki ortalama | `avg_previous` | avg_prev, avg_last_10, avg_last_amounts |
| Minimum sok esigi | `min_volume_shock` | hacim_sok_esigi, hacim_soku_min_esik, insider_hacim_sok_esigi |

### 5. Sharp Score Bileenleri
| Kavram | CANONICAL ISIM | Eski/Yanlis Isimler (KALDIRILACAK) |
|--------|----------------|-----------------------------------|
| Sharp skoru | `sharp_score` | smart_score, real_sharp_score, sharpScore, sharp_score_value |
| Hacim katkisi | `volume_contrib` | volume_contribution |
| Oran katkisi | `odds_contrib` | odds_contribution |
| Pay katkisi | `share_contrib` | share_contribution |

### 6. Alarm Metadata
| Kavram | CANONICAL ISIM | Eski/Yanlis Isimler (KALDIRILACAK) |
|--------|----------------|-----------------------------------|
| Olusturulma zamani | `created_at` | trigger_at (FARKLI: tetiklenme ani) |
| Tetiklenme zamani | `trigger_at` | event_time (FARKLI: olay zamani) |
| Mac tarihi | `match_date` | date, fixture_date |

---

## ALARM TURLERI VE KULLANILAN FIELDLAR

### 1. SHARP ALARMS
**Tetiklenme Kriterleri:**
- `incoming_money >= min_incoming_money` (default: 1999)
- `odds_drop_pct >= min_odds_drop_pct` (orana gore degisir)
- `share_change > 0`
- `sharp_score >= min_sharp_score` (default: 30)

**Supabase Kolonlari:**
```
id, home, away, market, selection
sharp_score, volume_contrib, odds_contrib, share_contrib
incoming_money, previous_amount, current_amount
opening_odds, previous_odds, current_odds, odds_drop_pct
previous_share, current_share, share_change
volume_shock, volume_shock_multiplier, avg_previous
match_date, trigger_at, created_at, alarm_type
```

### 2. INSIDER ALARMS
**Tetiklenme Kriterleri:**
- `volume_shock < min_volume_shock` (default: 0.2 - dusuk sok = sessiz para)
- `odds_drop_pct >= min_odds_drop_pct` (default: 7%)
- `incoming_money < max_incoming_money` (default: 100)
- `current_odds < max_current_odds` (default: 1.9)

**Supabase Kolonlari:**
```
id, home, away, market, selection
odds_drop_pct, incoming_money, volume_shock, avg_volume_shock
opening_odds, current_odds
surrounding_snapshots (JSONB), snapshot_count
drop_moment, match_date, trigger_at, created_at, alarm_type
```

### 3. VOLUMESHOCK ALARMS
**Tetiklenme Kriterleri:**
- `volume_shock >= min_volume_shock` (default: 5x)
- `hours_to_kickoff >= min_hours` (default: 3 saat)
- `incoming_money >= min_incoming_money`

**Supabase Kolonlari:**
```
id, home, away, market, selection
volume_shock, volume_shock_multiplier
incoming_money, avg_previous
hours_to_kickoff
match_date, trigger_at, created_at, alarm_type
```

### 4. BIGMONEY ALARMS
**Tetiklenme Kriterleri:**
- `incoming_money >= limit` (default: 15000)

**Supabase Kolonlari:**
```
id, home, away, market, selection
incoming_money, selection_total
is_huge, huge_total
match_date, trigger_at, created_at, alarm_type
```

### 5. DROPPING ALARMS
**Tetiklenme Kriterleri:**
- L1: `odds_drop_pct >= 10% && < 17%`
- L2: `odds_drop_pct >= 17% && < 20%`
- L3: `odds_drop_pct >= 20%`

**Supabase Kolonlari:**
```
id, home, away, market, selection
opening_odds, current_odds, odds_drop_pct
level (L1/L2/L3)
match_date, trigger_at, created_at, alarm_type
```

### 6. PUBLICMOVE ALARMS
**Tetiklenme Kriterleri:**
- `trap_score >= min_trap_score` (default: 70)

**Supabase Kolonlari:**
```
id, home, away, market, selection
trap_score, incoming_money, odds_drop_pct
previous_share, current_share, share_change
match_date, trigger_at, created_at, alarm_type
```

### 7. VOLUMELEADER ALARMS
**Tetiklenme Kriterleri:**
- Lider degisimi (eski lider != yeni lider)
- `new_leader_share >= leader_threshold` (default: 50%)

**Supabase Kolonlari:**
```
id, home, away, market
old_leader, old_leader_share
new_leader, new_leader_share
total_volume
match_date, trigger_at, created_at, alarm_type
```

---

## UYGULAMA PLANI

### Adim 1: Config Dosyalari
- sharp_config.json: min_amount_change -> min_incoming_money
- insider_config.json: oran_dusus_esigi -> min_odds_drop_pct, hacim_sok_esigi -> min_volume_shock
- volume_shock_config.json: hacim_soku_min_esik -> min_volume_shock

### Adim 2: Backend (app.py, alarm_calculator.py)
- Tum hesaplama fonksiyonlarinda canonical isimlere gec
- Eski isimleri alias olarak destekle (gecis donemi)

### Adim 3: Supabase Mapping (supabase_client.py)
- write_*_alarms_to_supabase fonksiyonlarini guncelle
- Canonical isimleri kullan

### Adim 4: Supabase Schema
- Kolon isimlerini canonical isimlere degistir (ALTER TABLE)
- Eski kolonlari koru (backward compatibility)

### Adim 5: Admin Panel
- Gosterilen field isimlerini canonical isimlere esle
- Turkce label'lar: incoming_money -> "Gelen Para", odds_drop_pct -> "Oran Dususu %"
