"""
SmartXFlow Unified Alarm Model
==============================

Ortak alarm modeli ve builder fonksiyonları.
Tüm alarm tipleri (Sharp, Dropping, Reversal) aynı JSON yapısını kullanır.

Alarm JSON Yapısı:
{
    "id": "uuid",
    "match_id": "Home|Away|League|Date",
    "market": "1x2 | ou25 | btts",
    "side": "1 | X | 2 | Over | Under | Yes | No",
    "category": "sharp | dropping | reversal",
    "is_alarm": True/False,       # Gerçek alarm mı?
    "is_preview": True/False,     # Sadece preview mi?
    "severity": 1-3,              # L1/L2/L3
    "score": 0-100,               # Sharp score veya drop yüzdesi
    "conditions_met": 0-3,        # Reversal için kriter sayısı
    "message": "...",             # Gösterilecek mesaj
    "created_at": "ISO timestamp",
    "extra": {}                   # Ek detaylar
}
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any


MARKET_VOLUME_THRESHOLDS = {
    '1x2': 5000,
    'ou25': 3000,
    'btts': 2000
}

DROPPING_LEVEL_THRESHOLDS = {
    'L1': (7, 10),
    'L2': (10, 15),
    'L3': (15, 100)
}

DROPPING_PERSISTENCE_MINUTES = 30


def get_dropping_level(drop_pct: float) -> int:
    """
    Drop yüzdesine göre seviye hesapla.
    
    < 7%  → 0 (gösterme)
    7-10% → 1 (L1)
    10-15% → 2 (L2)
    15%+  → 3 (L3)
    """
    if drop_pct < 7:
        return 0
    elif drop_pct < 10:
        return 1
    elif drop_pct < 15:
        return 2
    else:
        return 3


def create_base_alarm(
    match_id: str,
    market: str,
    side: str,
    category: str,
    is_alarm: bool,
    message: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Temel alarm objesi oluştur.
    Tüm alarm tipleri bu fonksiyonu kullanır.
    """
    return {
        'id': str(uuid.uuid4()),
        'match_id': match_id,
        'market': market,
        'side': side,
        'category': category,
        'is_alarm': is_alarm,
        'is_preview': kwargs.get('is_preview', False),
        'severity': kwargs.get('severity', 1),
        'score': kwargs.get('score', 0),
        'conditions_met': kwargs.get('conditions_met', 0),
        'message': message,
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'extra': kwargs.get('extra', {})
    }


def build_sharp_alarm(
    match_id: str,
    market: str,
    side: str,
    sharp_score: float,
    criteria_flags: Dict[str, bool],
    total_volume: float
) -> List[Dict[str, Any]]:
    """
    Sharp alarm objesi oluştur.
    
    Args:
        match_id: Maç ID'si (Home|Away|League|Date)
        market: Market tipi (1x2, ou25, btts)
        side: Seçim (1, X, 2, Over, Under, Yes, No)
        sharp_score: 0-100 arası skor
        criteria_flags: {
            "volume_shock": True/False,     # 2x+ hacim şoku
            "odds_drop": True/False,        # %1+ oran düşüşü
            "share_shift": True/False       # +2pt pay artışı
        }
        total_volume: Market toplam hacmi
        
    Returns:
        Liste (boş veya 1 elemanlı)
        
    Kurallar:
        - sharp_score >= 20 → GERÇEK ALARM (skor bazlı)
        - sharp_score < 20 → Hiç üretme
        
    NOT: Kriter kontrolü DEVRE DIŞI - sadece skor bazlı alarm
    """
    market_key = market.replace('moneyway_', '').replace('dropping_', '')
    min_volume = MARKET_VOLUME_THRESHOLDS.get(market_key, 5000)
    
    if total_volume < min_volume:
        return []
    
    if sharp_score < 20:
        return []
    
    all_criteria_met = all(criteria_flags.values())
    criteria_count = sum(1 for v in criteria_flags.values() if v)
    
    # Skor 20+ = GERÇEK ALARM
    if sharp_score >= 70:
        severity = 3 if sharp_score >= 85 else 2
    elif sharp_score >= 50:
        severity = 2
    else:
        severity = 1
    
    return [create_base_alarm(
        match_id=match_id,
        market=market,
        side=side,
        category='sharp',
        is_alarm=True,
        is_preview=False,
        severity=severity,
        score=int(sharp_score),
        message=f"Sharp {int(sharp_score)}/100",
        extra={
            'criteria': criteria_flags,
            'criteria_count': criteria_count,
            'total_volume': total_volume,
            'all_criteria_met': all_criteria_met
        }
    )]


def build_dropping_alarm(
    match_id: str,
    market: str,
    side: str,
    drop_pct: float,
    minutes_persisted: float
) -> Optional[Dict[str, Any]]:
    """
    Dropping alarm objesi oluştur.
    
    Args:
        match_id: Maç ID'si
        market: Market tipi
        side: Seçim
        drop_pct: Drop yüzdesi (0-100)
        minutes_persisted: Kaç dakikadır %7+ üstünde
        
    Returns:
        Alarm objesi veya None
        
    Kurallar:
        - drop_pct < 7% → None (hiç üretme)
        - 30dk dolmadan → is_preview=True, is_alarm=False
        - 30dk dolduktan sonra → is_alarm=True, is_preview=False
    """
    level = get_dropping_level(drop_pct)
    
    if level == 0:
        return None
    
    is_real = minutes_persisted >= DROPPING_PERSISTENCE_MINUTES
    
    if is_real:
        message = f"Dropping L{level} – {drop_pct:.1f}% (30dk+ kalıcı)"
    else:
        message = f"Dropping L{level} – {drop_pct:.1f}% ({int(minutes_persisted)}/{DROPPING_PERSISTENCE_MINUTES}dk, preview)"
    
    return create_base_alarm(
        match_id=match_id,
        market=market,
        side=side,
        category='dropping',
        is_alarm=is_real,
        is_preview=not is_real,
        severity=level,
        score=round(drop_pct, 1),
        message=message,
        extra={
            'drop_pct': round(drop_pct, 1),
            'minutes_persisted': round(minutes_persisted, 1),
            'level': level,
            'level_name': f'L{level}'
        }
    )


def build_reversal_alarm(
    match_id: str,
    market: str,
    side: str,
    conditions: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Reversal Move alarm objesi oluştur.
    
    Args:
        match_id: Maç ID'si
        market: Market tipi
        side: Seçim
        conditions: {
            "reversal_pct": float,         # Geri dönüş yüzdesi (>=50 gerekli)
            "momentum_changed": bool,      # Trend değişti mi?
            "volume_switched": bool        # Hacim taraf değiştirdi mi?
        }
        
    Returns:
        Alarm objesi (her zaman döner, is_alarm değişir)
        
    Kurallar:
        - 3/3 kriter → is_alarm=True (GERÇEK ALARM)
        - 0-2/3 kriter → is_alarm=False (sadece log)
    """
    reversal_pct = conditions.get('reversal_pct', 0)
    momentum_changed = conditions.get('momentum_changed', False)
    volume_switched = conditions.get('volume_switched', False)
    
    conditions_met = 0
    criteria_details = []
    
    if reversal_pct >= 50:
        conditions_met += 1
        criteria_details.append(f"Retracement: {reversal_pct:.1f}%")
    
    if momentum_changed:
        conditions_met += 1
        criteria_details.append("Momentum: Değişti")
    
    if volume_switched:
        conditions_met += 1
        criteria_details.append("Volume Switch: Evet")
    
    is_alarm = conditions_met == 3
    
    if is_alarm:
        message = f"Trend tersine döndü — 3/3 kriter (Reversal Move)"
        severity = 3
    else:
        message = f"Reversal denemesi — {conditions_met}/3 kriter (sadece log)"
        severity = 1
    
    return create_base_alarm(
        match_id=match_id,
        market=market,
        side=side,
        category='reversal',
        is_alarm=is_alarm,
        is_preview=False,
        severity=severity,
        score=0,
        conditions_met=conditions_met,
        message=message,
        extra={
            'reversal_pct': round(reversal_pct, 1),
            'momentum_changed': momentum_changed,
            'volume_switched': volume_switched,
            'criteria_details': criteria_details,
            'criteria_text': ' | '.join(criteria_details)
        }
    )


def generate_example_alarms() -> List[Dict[str, Any]]:
    """
    Örnek alarm listesi üret (test ve dokümantasyon için).
    """
    alarms = []
    
    sharp1 = build_sharp_alarm(
        match_id="Liverpool|Arsenal|EPL|29.11.2025",
        market="moneyway_1x2",
        side="1",
        sharp_score=86,
        criteria_flags={
            "volume_shock": True,
            "market_share": True,
            "odds_drop": True,
            "share_shift": True
        },
        total_volume=15000
    )
    alarms.extend(sharp1)
    
    sharp2 = build_sharp_alarm(
        match_id="Chelsea|Tottenham|EPL|29.11.2025",
        market="moneyway_1x2",
        side="X",
        sharp_score=55,
        criteria_flags={
            "volume_shock": True,
            "market_share": True,
            "odds_drop": False,
            "share_shift": True
        },
        total_volume=12000
    )
    alarms.extend(sharp2)
    
    sharp3 = build_sharp_alarm(
        match_id="ManCity|Leeds|EPL|29.11.2025",
        market="moneyway_1x2",
        side="1",
        sharp_score=35,
        criteria_flags={
            "volume_shock": True,
            "market_share": False,
            "odds_drop": False,
            "share_shift": False
        },
        total_volume=8000
    )
    alarms.extend(sharp3)
    
    drop1 = build_dropping_alarm(
        match_id="Barcelona|RealMadrid|LaLiga|29.11.2025",
        market="moneyway_1x2",
        side="1",
        drop_pct=8.5,
        minutes_persisted=45
    )
    if drop1:
        alarms.append(drop1)
    
    drop2 = build_dropping_alarm(
        match_id="Juventus|Milan|SerieA|29.11.2025",
        market="moneyway_1x2",
        side="2",
        drop_pct=12.3,
        minutes_persisted=15
    )
    if drop2:
        alarms.append(drop2)
    
    drop3 = build_dropping_alarm(
        match_id="PSG|Lyon|Ligue1|29.11.2025",
        market="moneyway_1x2",
        side="X",
        drop_pct=18.5,
        minutes_persisted=60
    )
    if drop3:
        alarms.append(drop3)
    
    rev1 = build_reversal_alarm(
        match_id="Dortmund|Bayern|Bundesliga|29.11.2025",
        market="moneyway_1x2",
        side="2",
        conditions={
            "reversal_pct": 75.0,
            "momentum_changed": True,
            "volume_switched": True
        }
    )
    alarms.append(rev1)
    
    rev2 = build_reversal_alarm(
        match_id="Ajax|PSV|Eredivisie|29.11.2025",
        market="moneyway_1x2",
        side="1",
        conditions={
            "reversal_pct": 60.0,
            "momentum_changed": False,
            "volume_switched": True
        }
    )
    alarms.append(rev2)
    
    rev3 = build_reversal_alarm(
        match_id="Porto|Benfica|Liga|29.11.2025",
        market="moneyway_1x2",
        side="X",
        conditions={
            "reversal_pct": 30.0,
            "momentum_changed": False,
            "volume_switched": False
        }
    )
    alarms.append(rev3)
    
    return alarms


def filter_real_alarms(alarms: List[Dict]) -> List[Dict]:
    """
    Sadece gerçek alarmları filtrele (is_alarm === True).
    Frontend Alarm Listesi için kullanılır.
    """
    return [a for a in alarms if a.get('is_alarm', False) is True]


def filter_preview_alarms(alarms: List[Dict]) -> List[Dict]:
    """
    Sadece preview/log alarmları filtrele (is_alarm === False).
    Maç detayı "Alarm Geçmişi / Log" alanı için kullanılır.
    """
    return [a for a in alarms if a.get('is_alarm', False) is False]


if __name__ == '__main__':
    import json
    
    print("=" * 60)
    print("ÖRNEK ALARM ÜRETİMİ")
    print("=" * 60)
    
    examples = generate_example_alarms()
    
    print(f"\nToplam {len(examples)} alarm üretildi:\n")
    
    for alarm in examples:
        print(json.dumps(alarm, indent=2, ensure_ascii=False))
        print("-" * 40)
    
    print("\n" + "=" * 60)
    print("GERÇEK ALARMLAR (Alarm Listesi'nde görünecek)")
    print("=" * 60)
    
    real_alarms = filter_real_alarms(examples)
    print(f"\n{len(real_alarms)} gerçek alarm:\n")
    
    for alarm in real_alarms:
        print(f"  [{alarm['category'].upper()}] {alarm['message']}")
        print(f"    Match: {alarm['match_id'].split('|')[0]} vs {alarm['match_id'].split('|')[1]}")
        print(f"    Side: {alarm['side']}, Severity: L{alarm['severity']}")
        print()
    
    print("\n" + "=" * 60)
    print("PREVIEW / LOG ALARMLAR (Maç detayında görünecek)")
    print("=" * 60)
    
    preview_alarms = filter_preview_alarms(examples)
    print(f"\n{len(preview_alarms)} preview/log alarm:\n")
    
    for alarm in preview_alarms:
        print(f"  [{alarm['category'].upper()}] {alarm['message']}")
        print(f"    Match: {alarm['match_id'].split('|')[0]} vs {alarm['match_id'].split('|')[1]}")
        print()
