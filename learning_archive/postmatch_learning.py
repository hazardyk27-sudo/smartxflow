from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any


_TOTAL_LINE_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)")


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


def _parse_utc(value: str) -> datetime:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("postmatch learning observed_at must include timezone")
    return parsed.astimezone(timezone.utc)


def postmatch_learning_filename(observed_at: str) -> str:
    dt = _parse_utc(observed_at)
    stamp = dt.strftime("%Y%m%dT%H%M%S")
    if dt.microsecond:
        stamp += "." + f"{dt.microsecond:06d}".rstrip("0")
    return f"addenda/{stamp}Z-postmatch-learning.json"


def _source_name(row: dict[str, Any]) -> str:
    return _norm(row.get("_archive_source_table") or row.get("source_table") or "")


def _last_row(snapshots: list[dict[str, Any]], token: str) -> dict[str, Any] | None:
    found = [row for row in snapshots if token in _source_name(row)]
    return found[-1] if found else None


def _native_state(case: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    prediction = case.get("prediction") or {}
    match = case.get("match") or {}
    market = str(prediction.get("market") or "").strip()
    selection = str(prediction.get("selection") or "").strip()
    market_norm = _norm(market)
    selection_norm = _norm(selection)

    row: dict[str, Any] | None = None
    fields: tuple[str, str, str] | None = None
    native_market = market

    if market_norm in {"1x2", "matchodds", "fulltimeresult"}:
        row = _last_row(snapshots, "moneyway1x2")
        home = _norm(match.get("home"))
        away = _norm(match.get("away"))
        if selection_norm in {"1", "home", home}:
            fields = ("odds1", "pct1", "amt1")
        elif selection_norm in {"x", "draw"}:
            fields = ("oddsx", "pctx", "amtx")
        elif selection_norm in {"2", "away", away}:
            fields = ("odds2", "pct2", "amt2")
    elif "btts" in market_norm or "bothteamstoscore" in market_norm or market_norm == "kg":
        row = _last_row(snapshots, "moneywaybtts")
        if selection_norm in {"yes", "bttsyes", "var", "kgvar"}:
            fields = ("yes", "pctyes", "amtyes")
        elif selection_norm in {"no", "bttsno", "yok", "kgyok"}:
            fields = ("no", "pctno", "amtno")
    elif "overunder" in market_norm or market_norm.startswith("ou"):
        lines = _TOTAL_LINE_RE.findall(market + " " + selection)
        line = float(lines[-1]) if lines else None
        if line == 2.5:
            row = _last_row(snapshots, "moneywayou25")
            if selection_norm.startswith("over") or "ust" in selection_norm:
                fields = ("over", "pctover", "amtover")
            elif selection_norm.startswith("under") or "alt" in selection_norm:
                fields = ("under", "pctunder", "amtunder")
            native_market = "O/U 2.5"

    if row is None or fields is None:
        native_sources = sorted({
            str(item.get("_archive_source_table") or "")
            for item in snapshots
            if str(item.get("_archive_source_table") or "").strip()
        })
        return {
            "native": False,
            "unavailable_reason": (
                "Selected execution market is not a native SmartXFlow evidence market; "
                "no synthetic execution-market history or price was fabricated."
            ),
            "underlying_native_sources": native_sources,
        }

    price_field, share_field, money_field = fields
    observed_at = (
        row.get("scraped_at")
        or row.get("scraped_at_utc")
        or row.get("observed_at")
        or row.get("created_at")
    )
    return {
        "native": True,
        "market": native_market,
        "observed_at": observed_at,
        "price": row.get(price_field),
        "share": row.get(share_field),
        "money": row.get(money_field),
        "market_volume": row.get("volume"),
        "source_table": row.get("_archive_source_table"),
    }


def _stage2_check(case: dict[str, Any]) -> str:
    supports = 0
    contradicts = 0
    for item in case.get("evidence") or []:
        relationship = str((item or {}).get("relationship") or "").upper()
        if relationship == "SUPPORTS":
            supports += 1
        elif relationship == "CONTRADICTS":
            contradicts += 1
    if supports and contradicts:
        label = "MIXED"
    elif supports:
        label = "SUPPORTED"
    elif contradicts:
        label = "CONTRADICTED"
    else:
        label = "UNEXPLAINED"
    return f"{label}: Stage 2 archived evidence contains {supports} supporting and {contradicts} contradicting item(s)."


def _comparison(case: dict[str, Any], state: dict[str, Any]) -> str:
    prediction = case.get("prediction") or {}
    if not state.get("native"):
        return "No honest selected-market closing comparison is available because the execution market is non-native."
    entry = prediction.get("entry_odds")
    final_price = state.get("price")
    details = []
    if entry is not None and final_price not in (None, ""):
        details.append(f"entry_odds={entry}; final_prematch_price={final_price}")
    if state.get("share") not in (None, ""):
        details.append(f"final_share={state['share']}")
    if state.get("money") not in (None, ""):
        details.append(f"final_money={state['money']}")
    if state.get("market_volume") not in (None, ""):
        details.append(f"final_market_volume={state['market_volume']}")
    return "; ".join(details) if details else "Native final-prematch state was preserved, but comparable price/money fields were unavailable."


def build_postmatch_learning_note(
    case: dict[str, Any],
    snapshots: list[dict[str, Any]],
    *,
    observed_at: str,
) -> dict[str, Any]:
    settlement = case.get("settlement") or {}
    prediction = case.get("prediction") or {}
    final_score = str(settlement.get("final_score") or "").strip()
    if not final_score:
        raise ValueError("postmatch learning requires settlement.final_score")

    state = _native_state(case, snapshots)
    decision = str(prediction.get("decision") or "").upper()
    hypothetical = settlement.get("hypothetical_result")
    outcome = settlement.get("status") if decision == "BET" else hypothetical
    if decision == "WATCH":
        relevance = (
            f"Original WATCH remains immutable; the watched selection would have settled {hypothetical}."
        )
    else:
        relevance = f"Original BET settled {settlement.get('status')} on final score {final_score}."

    selected_market = {
        "market": prediction.get("market"),
        "selection": prediction.get("selection"),
        "entry_odds": prediction.get("entry_odds"),
    }
    if prediction.get("minimum_acceptable_odds") is not None:
        selected_market["minimum_acceptable_odds"] = prediction.get("minimum_acceptable_odds")

    return {
        "observed_at": observed_at,
        "case_id": case.get("case_id"),
        "type": "OBSERVATION",
        "final_score": final_score,
        "decision": decision,
        "settlement_status": settlement.get("status"),
        "hypothetical_result": hypothetical,
        "selected_market": selected_market,
        "final_prematch_sxf": state,
        "prediction_to_final_prematch_comparison": _comparison(case, state),
        "stage2_context_check": _stage2_check(case),
        "result_relevance": relevance,
        "learning": (
            f"Observed outcome for the frozen thesis/execution was {outcome}. "
            "Preserve this as case evidence; do not promote a method change from one result."
        ),
    }
