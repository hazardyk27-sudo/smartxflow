from __future__ import annotations

from typing import Any


def _price_text(preference: dict[str, Any], price_evidence: dict[str, Any] | None = None) -> str:
    evidence = price_evidence or {}
    price = evidence.get("price")
    if not isinstance(price, (int, float)):
        price = preference.get("price")
    if isinstance(price, (int, float)):
        return f" @{price:g}"
    threshold = evidence.get("minimum_acceptable_price")
    if isinstance(threshold, (int, float)):
        return f" | minimum {threshold:g}"
    return ""


def render_stage1(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    text: list[str] = ["STAGE 1 — SXF ADAYLARI"]
    by_id = {
        str(item.get("fixture_id") or item.get("fixture_uid") or item.get("match_id_hash") or ""): item
        for item in payload.get("screening_results") or []
        if isinstance(item, dict)
    }
    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or "")
        pref = match.get("preference") or {}
        screening = by_id.get(fixture_id, {})
        row = {
            "fixture_id": fixture_id,
            "preference": pref,
            "attention_signals": list(screening.get("attention_signals") or []),
            "rationale": match.get("rationale"),
            "strongest_counterargument": match.get("strongest_counterargument"),
        }
        rows.append(row)
        text.extend(
            [
                "",
                f"{fixture_id}",
                f"SXF TERCİHİ: {pref.get('selection')} | {pref.get('market')}{_price_text(pref)}",
                f"DİKKAT: {', '.join(row['attention_signals']) or '—'}",
                f"GEREKÇE: {row['rationale']}",
                f"EN GÜÇLÜ SXF KARŞI TEZ: {row['strongest_counterargument']}",
            ]
        )
    return {"stage": "STAGE1", "rows": rows, "text": "\n".join(text)}


def render_stage2(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    text: list[str] = ["STAGE 2 — ODAKLI ARAŞTIRMA"]
    coverage_tr = {"HIGH": "YÜKSEK", "MEDIUM": "ORTA", "LOW": "DÜŞÜK"}
    verdict_tr = {
        "CONFIRMED": "DOĞRULANDI",
        "PARTIALLY_CONFIRMED": "KISMEN DOĞRULANDI",
        "CONTRADICTED": "ÇELİŞTİ",
        "UNEXPLAINED": "AÇIKLANAMADI",
    }
    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or "")
        frozen = match.get("frozen_stage1_preference") or {}
        coverage = str(match.get("coverage") or "").upper()
        verdict = str(match.get("verdict") or "").upper()
        row = {
            "fixture_id": fixture_id,
            "frozen_stage1_preference": frozen,
            "research_support": match.get("research_support"),
            "research_counter": match.get("research_counter"),
            "important_absence": match.get("important_absence"),
            "coverage": coverage,
            "verdict": verdict,
            "facts": match.get("facts") or [],
        }
        rows.append(row)
        text.extend(
            [
                "",
                fixture_id,
                f"SXF NE DİYOR: {frozen.get('selection')} | {frozen.get('market')}",
                f"ARAŞTIRMA DESTEĞİ: {row['research_support']}",
                f"EN GÜÇLÜ ÇELİŞKİ: {row['research_counter']}",
                f"ÖNEMLİ EKSİK: {row['important_absence'] or 'Yok / material değil'}",
                f"ARAŞTIRMA KAPSAMI: {coverage_tr.get(coverage, coverage)}",
                f"2. AŞAMA SONUCU: {verdict_tr.get(verdict, verdict)}",
            ]
        )
    return {"stage": "STAGE2", "rows": rows, "text": "\n".join(text)}


def render_stage3(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    text: list[str] = ["STAGE 3 — NİHAİ KARAR"]
    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or "")
        pref = match.get("preference") or {}
        price_evidence = match.get("price_evidence") if isinstance(match.get("price_evidence"), dict) else None
        row = {
            "fixture_id": fixture_id,
            "preference": pref,
            "decision": match.get("decision"),
            "grade": match.get("grade"),
            "final_confidence": match.get("final_confidence"),
            "counter_severity": match.get("counter_severity"),
            "divergence_state": match.get("divergence_state"),
            "execution_type": match.get("execution_type"),
            "rationale": match.get("rationale"),
            "strongest_counterargument": match.get("strongest_counterargument"),
            "change_driver": match.get("change_driver"),
            "price_evidence": price_evidence,
        }
        rows.append(row)
        text.extend(
            [
                "",
                fixture_id,
                f"TERCİH: {pref.get('selection')} | {pref.get('market')}{_price_text(pref, price_evidence)}",
                f"KARAR: {row['decision']} | GRADE: {row['grade']} | GÜVEN: {row['final_confidence']}",
                f"DIVERGENCE: {row['divergence_state']} | EXECUTION: {row['execution_type']}",
                f"GEREKÇE: {row['rationale']}",
                f"EN GÜÇLÜ KARŞI ARGÜMAN: {row['strongest_counterargument']}",
            ]
        )
    return {"stage": "STAGE3", "rows": rows, "text": "\n".join(text)}


def render_payload(payload: dict[str, Any]) -> dict[str, Any]:
    stage = str(payload.get("stage") or "").upper()
    if stage == "STAGE1":
        return render_stage1(payload)
    if stage == "STAGE2":
        return render_stage2(payload)
    if stage == "STAGE3":
        return render_stage3(payload)
    raise ValueError(f"unsupported stage: {stage!r}")
