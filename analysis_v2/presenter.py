"""Analysis V2 Part 10: stable UI presenter.

Transforms immutable V2 ledger rows into a small, explicit card contract so the
browser never needs to understand raw engine JSON shapes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional


UI_CONTRACT_VERSION = "analysis-v2-ui-1.0.0"

STATE_META = {
    "FIRSAT": {
        "label": "FIRSAT",
        "tone": "opportunity",
        "summary": "Çekirdek hareket ve çapraz piyasa teyidi aynı yönde.",
    },
    "IZLE": {
        "label": "İZLE",
        "tone": "watch",
        "summary": "Yön var ancak teyit veya risk tarafı henüz temiz değil.",
    },
    "UZAK_DUR": {
        "label": "UZAK DUR",
        "tone": "avoid",
        "summary": "Çekirdek piyasada ciddi çelişki veya ters fiyat davranışı var.",
    },
    "UNKNOWN": {
        "label": "VERİ YETERSİZ",
        "tone": "muted",
        "summary": "Kartı sınıflandırmak için yeterli V2 kanıtı yok.",
    },
}

COMPONENT_LABELS = {
    "price_confirmation": "Fiyat Teyidi",
    "money_flow": "Para Akışı",
    "timing": "Zamanlama",
    "cross_market": "Cross-Market",
    "poly": "Poly",
    "risk": "Risk",
}

LEVEL_LABELS = {
    "STRONG": "Güçlü",
    "MEDIUM": "Orta",
    "WEAK": "Zayıf",
    "NEUTRAL": "Nötr",
    "MIXED": "Karışık",
    "CONFLICT": "Çelişki",
    "UNAVAILABLE": "Veri yok",
    "UNKNOWN": "Veri yok",
}

REASON_TEXT = {
    "CORE_AND_CROSS_MARKET_CONFIRMED": "Ana piyasa ve çapraz marketler aynı yönü teyit ediyor.",
    "CONFIRMATION_INCOMPLETE_OR_RISK_PRESENT": "Hareket var fakat teyit zinciri tamamlanmış değil.",
    "HARD_MARKET_CONTRADICTION": "Piyasa içinde sonucu zayıflatan ciddi bir çelişki var.",
    "MEANINGFUL_PRICE_SHORTENING": "Oran anlamlı biçimde kısaldı.",
    "MODERATE_PRICE_SHORTENING": "Oranda orta seviyede kısalma var.",
    "LARGE_CONFIRMED_MONEY_INFLOW": "Seçime güçlü yeni para girişi var.",
    "MEANINGFUL_MONEY_INFLOW": "Seçime anlamlı yeni para girişi var.",
    "MULTI_MARKET_DIRECTION_CONFIRMED": "Birden fazla gerçek yön marketi aynı tarafı destekliyor.",
    "ONLY_ONE_DIRECTIONAL_MARKET": "Yön yalnız tek gerçek market tarafından destekleniyor.",
    "POLY_MULTI_COMPONENT_SUPPORT": "Polymarket tarafında birden fazla bağımsız bileşen destek veriyor.",
    "POLY_MULTI_COMPONENT_CONFLICT": "Polymarket tarafı ana yönle anlamlı biçimde çelişiyor.",
    "POLY_INTERNAL_DISAGREEMENT": "Polymarket bileşenleri kendi içinde ayrışıyor.",
    "PRICE_MOVES_AGAINST_MONEY": "Para gelirken oran ters yönde açılıyor.",
    "DIRECTIONAL_MARKETS_CONFLICT": "Aynı yönü ifade eden gerçek marketler birbiriyle çelişiyor.",
}


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 2) -> Optional[float]:
    number = _number(value)
    return round(number, digits) if number is not None else None


def _timestamp(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _confidence(row: Mapping[str, Any]) -> Dict[str, Any]:
    features = _dict(row.get("features"))
    confidence = _dict(features.get("explainable_confidence"))
    if confidence:
        return confidence

    reason = _dict(row.get("engine_reason"))
    legacy = _dict(reason.get("explainable_confidence"))
    return legacy


def _classification(row: Mapping[str, Any]) -> Dict[str, Any]:
    features = _dict(row.get("features"))
    classification = _dict(features.get("classification"))
    reason = _dict(row.get("engine_reason"))
    if reason.get("primary_class") and not classification.get("primary_class"):
        classification["primary_class"] = reason.get("primary_class")
    if reason.get("decision_window") and not classification.get("decision_window"):
        classification["decision_window"] = reason.get("decision_window")
    return classification


def _movement(row: Mapping[str, Any]) -> Dict[str, Any]:
    return _dict(_dict(row.get("features")).get("market_movement"))


def _state(row: Mapping[str, Any]) -> str:
    confidence = _confidence(row)
    reason = _dict(row.get("engine_reason"))
    reason_confidence = _dict(reason.get("explainable_confidence"))
    state = str(
        confidence.get("user_state")
        or reason_confidence.get("user_state")
        or ""
    ).upper()
    return state if state in STATE_META else "UNKNOWN"


def _decision_window(row: Mapping[str, Any]) -> Optional[str]:
    classification = _classification(row)
    reason = _dict(row.get("engine_reason"))
    window = classification.get("decision_window") or reason.get("decision_window")
    if window in {"30m", "2h", "6h", "open"}:
        return str(window)
    return None


def _component_cards(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    components = _dict(_confidence(row).get("components"))
    cards = []
    for key, label in COMPONENT_LABELS.items():
        source = _dict(components.get(key))
        level = str(source.get("level") or "UNKNOWN").upper()
        evidence = _dict(source.get("evidence"))
        cards.append(
            {
                "key": key,
                "label": label,
                "level": level,
                "level_label": LEVEL_LABELS.get(level, level.title()),
                "reason_codes": list(source.get("reason_codes") or []),
                "evidence": evidence,
            }
        )
    return cards


def _risk_items(row: Mapping[str, Any]) -> List[Dict[str, str]]:
    for component in _component_cards(row):
        if component["key"] != "risk":
            continue
        items = component["evidence"].get("items")
        if not isinstance(items, list):
            return []
        output = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            output.append(
                {
                    "code": str(item.get("code") or ""),
                    "severity": str(item.get("severity") or "UNKNOWN").upper(),
                    "source": str(item.get("source") or ""),
                }
            )
        return output
    return []


def _why_lines(row: Mapping[str, Any]) -> List[str]:
    confidence = _confidence(row)
    reason_codes = list(confidence.get("state_reason_codes") or [])
    if not reason_codes:
        reason_codes = list(
            _dict(row.get("engine_reason"))
            .get("explainable_confidence", {})
            .get("state_reason_codes", [])
            if isinstance(
                _dict(row.get("engine_reason")).get("explainable_confidence"),
                Mapping,
            )
            else []
        )

    lines = []
    for code in reason_codes:
        lines.append(REASON_TEXT.get(str(code), str(code).replace("_", " ").title()))

    for component in _component_cards(row):
        if component["key"] in {"price_confirmation", "money_flow", "cross_market"}:
            for code in component["reason_codes"][:1]:
                text = REASON_TEXT.get(str(code))
                if text and text not in lines:
                    lines.append(text)
    return lines[:4]


def _flow(row: Mapping[str, Any]) -> List[Dict[str, str]]:
    components = {item["key"]: item for item in _component_cards(row)}
    money = components.get("money_flow", {})
    price = components.get("price_confirmation", {})
    cross = components.get("cross_market", {})

    if money.get("level") in {"STRONG", "MEDIUM", "WEAK"}:
        first = {"label": "PARA GELDİ", "tone": "positive"}
    elif money.get("level") == "CONFLICT":
        first = {"label": "PARA TERSİNE DÖNDÜ", "tone": "negative"}
    else:
        first = {"label": "PARA NET DEĞİL", "tone": "muted"}

    if price.get("level") in {"STRONG", "MEDIUM", "WEAK"}:
        second = {"label": "ORAN DÜŞTÜ", "tone": "positive"}
    elif price.get("level") == "CONFLICT":
        second = {"label": "ORAN TERSİNE GİTTİ", "tone": "negative"}
    else:
        second = {"label": "FİYAT TEYİTSİZ", "tone": "muted"}

    if cross.get("level") == "STRONG":
        third = {"label": "PİYASA TEYİT ETTİ", "tone": "positive"}
    elif cross.get("level") == "CONFLICT":
        third = {"label": "PİYASA ÇELİŞİYOR", "tone": "negative"}
    else:
        third = {"label": "TEYİT EKSİK", "tone": "watch"}

    return [first, second, third]


def _direction_copy(selection: str) -> str:
    return {
        "1": "Ev sahibi tarafı güçleniyor.",
        "1X": "Ev sahibi kaybetmeme tarafı güçleniyor.",
        "2": "Deplasman tarafı güçleniyor.",
        "X2": "Deplasman kaybetmeme tarafı güçleniyor.",
        "X": "Beraberlik tarafında baskı oluşuyor.",
        "12": "Beraberlik dışı sonuç tarafı güçleniyor.",
    }.get(selection, "Piyasa hareketi belirginleşiyor.")


def _movement_summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    window = _decision_window(row)
    movement = _movement(row)
    current = _dict(movement.get("current"))
    anchors = _dict(movement.get("anchors"))
    base = _dict(anchors.get(window)) if window and window != "open" else _dict(movement.get("opening"))
    moves = _dict(movement.get("movement"))
    move = _dict(moves.get(window)) if window else {}

    if not current:
        current = {
            "odds": row.get("trigger_odds"),
            "pct": row.get("trigger_pct"),
            "amount": row.get("trigger_amount"),
            "market_volume": row.get("trigger_volume"),
        }

    if not base and window:
        base = {
            "odds": row.get(f"odds_{window}"),
            "pct": row.get(f"pct_{window}"),
            "amount": row.get(f"amount_{window}"),
        }

    money_added = move.get("amount_delta")
    if money_added is None and window:
        money_added = row.get(f"money_added_{window}")

    pct_delta = move.get("pct_delta")
    price_drop = move.get("odds_drop_pct")

    return {
        "window": window,
        "base_odds": _round(base.get("odds"), 3),
        "current_odds": _round(current.get("odds"), 3),
        "money_added": _round(money_added, 2),
        "pct_delta": _round(pct_delta, 2),
        "price_drop_pct": _round(price_drop, 2),
        "current_pct": _round(current.get("pct"), 2),
        "current_amount": _round(current.get("amount"), 2),
        "market_volume": _round(current.get("market_volume"), 2),
    }


def present_signal(row: Mapping[str, Any]) -> Dict[str, Any]:
    state = _state(row)
    state_meta = STATE_META[state]
    recommended_market = str(
        row.get("recommended_market") or row.get("market_key") or ""
    ).upper()
    recommended_selection = str(
        row.get("recommended_selection") or row.get("selection_code") or ""
    ).upper()
    recommended_odds = _number(row.get("recommended_odds"))
    if recommended_odds is None:
        selector = _dict(_dict(row.get("features")).get("market_selector"))
        recommended_odds = _number(selector.get("recommended_odds"))
    if recommended_odds is None and (
        recommended_market == str(row.get("market_key") or "").upper()
        and recommended_selection == str(row.get("selection_code") or "").upper()
    ):
        recommended_odds = _number(row.get("trigger_odds"))

    confidence = _confidence(row)
    classification = _classification(row)
    risk_items = _risk_items(row)
    outcome = str(row.get("outcome") or "").upper() or None

    return {
        "signal_id": str(row.get("signal_id") or ""),
        "contract_version": UI_CONTRACT_VERSION,
        "state": state,
        "state_label": state_meta["label"],
        "state_tone": state_meta["tone"],
        "state_summary": state_meta["summary"],
        "home_team": str(row.get("home_team") or ""),
        "away_team": str(row.get("away_team") or ""),
        "league": str(row.get("league") or ""),
        "kickoff_utc": _timestamp(row.get("kickoff_utc")),
        "trigger_at": _timestamp(row.get("trigger_at")),
        "current_state": str(row.get("current_state") or ""),
        "outcome": outcome,
        "match": f"{row.get('home_team') or ''} — {row.get('away_team') or ''}",
        "recommendation": {
            "market": recommended_market,
            "selection": recommended_selection,
            "odds": _round(recommended_odds, 3),
            "direction_copy": _direction_copy(recommended_selection),
        },
        "flow": _flow(row),
        "movement": _movement_summary(row),
        "components": _component_cards(row),
        "why": _why_lines(row),
        "risks": risk_items,
        "details": {
            "primary_class": str(
                classification.get("primary_class")
                or _dict(row.get("engine_reason")).get("primary_class")
                or ""
            ).upper(),
            "decision_window": _decision_window(row),
            "risk_count": int(_number(confidence.get("risk_count")) or len(risk_items)),
            "engine_key": str(row.get("engine_key") or ""),
            "engine_version": str(row.get("engine_version") or ""),
            "source_market": str(row.get("market_key") or "").upper(),
            "source_selection": str(row.get("selection_code") or "").upper(),
        },
    }


def present_signal_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    cards = [present_signal(row) for row in rows]
    cards.sort(
        key=lambda card: (
            card.get("trigger_at") or "",
            card.get("signal_id") or "",
        ),
        reverse=True,
    )
    counts = {"FIRSAT": 0, "IZLE": 0, "UZAK_DUR": 0, "UNKNOWN": 0}
    for card in cards:
        counts[card["state"]] = counts.get(card["state"], 0) + 1
    return {
        "contract_version": UI_CONTRACT_VERSION,
        "count": len(cards),
        "counts": counts,
        "signals": cards,
    }



STATE_LABELS_TR = {
    "TRIGGERED": "Tetiklendi",
    "ACTIVE": "Aktif",
    "CONFIRMED": "Teyit Edildi",
    "WEAKENED": "Zayıfladı",
    "INVALIDATED": "Geçersizleşti",
    "SETTLED": "Sonuçlandı",
}


def _state_timeline_item(row: Mapping[str, Any]) -> Dict[str, Any]:
    state = str(row.get("state") or "").upper()
    return {
        "state": state,
        "label": STATE_LABELS_TR.get(state, state or "Bilinmiyor"),
        "state_at": _timestamp(row.get("state_at")),
        "current_odds": _round(row.get("current_odds"), 3),
        "current_pct": _round(row.get("current_pct"), 2),
        "current_amount": _round(row.get("current_amount"), 2),
        "current_volume": _round(row.get("current_volume"), 2),
        "reason_code": str(row.get("reason_code") or ""),
        "reason": _dict(row.get("reason")),
    }


def present_signal_detail(
    current_row: Mapping[str, Any],
    state_rows: Iterable[Mapping[str, Any]] = (),
    settlement_row: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an auditable exact-signal detail payload for the V2 drawer."""
    card = present_signal(current_row)
    timeline = [_state_timeline_item(row) for row in state_rows]
    timeline.sort(
        key=lambda item: (
            item.get("state_at") or "",
            item.get("state") or "",
        )
    )

    settlement_source = settlement_row or current_row
    outcome = str(settlement_source.get("outcome") or "").upper()
    settlement = None
    if outcome or settlement_source.get("settled_at"):
        settlement = {
            "outcome": outcome or None,
            "final_home_score": (
                int(settlement_source["final_home_score"])
                if settlement_source.get("final_home_score") is not None
                else None
            ),
            "final_away_score": (
                int(settlement_source["final_away_score"])
                if settlement_source.get("final_away_score") is not None
                else None
            ),
            "entry_odds": _round(settlement_source.get("entry_odds"), 3),
            "pnl_units": _round(settlement_source.get("pnl_units"), 3),
            "settled_at": _timestamp(settlement_source.get("settled_at")),
            "settlement_source": str(
                settlement_source.get("settlement_source") or ""
            ),
        }

    return {
        "contract_version": UI_CONTRACT_VERSION,
        "signal_id": card["signal_id"],
        "card": card,
        "timeline": timeline,
        "settlement": settlement,
        "audit": {
            "match_id_hash": str(current_row.get("match_id_hash") or ""),
            "engine_key": str(current_row.get("engine_key") or ""),
            "engine_version": str(current_row.get("engine_version") or ""),
            "source_market": str(current_row.get("market_key") or "").upper(),
            "source_selection": str(
                current_row.get("selection_code") or ""
            ).upper(),
            "trigger_at": _timestamp(current_row.get("trigger_at")),
            "trigger_odds": _round(current_row.get("trigger_odds"), 3),
            "trigger_pct": _round(current_row.get("trigger_pct"), 2),
            "trigger_amount": _round(current_row.get("trigger_amount"), 2),
            "trigger_volume": _round(current_row.get("trigger_volume"), 2),
            "recommended_market": card["recommendation"]["market"],
            "recommended_selection": card["recommendation"]["selection"],
            "recommended_odds": card["recommendation"]["odds"],
            "config_snapshot": _dict(current_row.get("config_snapshot")),
        },
    }
