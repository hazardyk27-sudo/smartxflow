from __future__ import annotations

from urllib.parse import urlparse
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


def _source_label(source: Any) -> str:
    raw = str(source or "").strip()
    if not raw:
        return "kaynak yok"
    try:
        host = (urlparse(raw).hostname or "").lower()
    except ValueError:
        host = ""
    return host or raw


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
    text: list[str] = ["STAGE 2 — KANITLI ODAKLI ARAŞTIRMA"]
    coverage_tr = {"HIGH": "YÜKSEK", "MEDIUM": "ORTA", "LOW": "DÜŞÜK"}
    verdict_tr = {
        "CONFIRMED": "DOĞRULANDI",
        "PARTIALLY_CONFIRMED": "KISMEN DOĞRULANDI",
        "CONTRADICTED": "ÇELİŞTİ",
        "UNEXPLAINED": "AÇIKLANAMADI",
    }
    relation_tr = {"SUPPORTS": "DESTEKLİYOR", "CONTRADICTS": "ÇELİŞİYOR", "NEUTRAL": "NÖTR"}
    category_tr = {
        "SQUAD": "KADRO",
        "LINEUP": "İLK 11",
        "MANAGER_COMMENT": "TEKNİK DİREKTÖR AÇIKLAMASI",
        "PERFORMANCE": "PERFORMANS",
        "TACTICAL": "TAKTİK",
        "CONTEXT": "BAĞLAM",
        "H2H": "H2H",
    }
    status_tr = {"VERIFIED": "DOĞRULANDI", "UNKNOWN": "BİLİNMİYOR"}

    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or "")
        frozen = match.get("frozen_stage1_preference") or {}
        coverage = str(match.get("coverage") or "").upper()
        verdict = str(match.get("verdict") or "").upper()
        facts = match.get("facts") or []
        checks = match.get("research_checks") if isinstance(match.get("research_checks"), dict) else {}
        row = {
            "fixture_id": fixture_id,
            "frozen_stage1_preference": frozen,
            "research_support": match.get("research_support"),
            "research_counter": match.get("research_counter"),
            "research_synthesis": match.get("research_synthesis"),
            "important_absence": match.get("important_absence"),
            "coverage": coverage,
            "verdict": verdict,
            "facts": facts,
            "research_checks": checks,
            "support_fact_ids": match.get("support_fact_ids") or [],
            "counter_fact_ids": match.get("counter_fact_ids") or [],
        }
        rows.append(row)
        text.extend(
            [
                "",
                fixture_id,
                f"SXF NE DİYOR: {frozen.get('selection')} | {frozen.get('market')}",
                "KANITLAR:",
            ]
        )
        for idx, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                continue
            kind = str(fact.get("kind") or "").upper()
            relationship = str(fact.get("relationship") or "").upper()
            category = str(fact.get("category") or "").upper()
            fact_id = str(fact.get("fact_id") or f"fact-{idx}")
            if kind == "FACT":
                evidence_at = str(fact.get("evidence_at") or "")
                text.append(
                    f"  {idx}. [{fact_id}] {category_tr.get(category, category)} | {relation_tr.get(relationship, relationship)} | "
                    f"{fact.get('claim')} | Kaynak: {_source_label(fact.get('source'))} (Tier {fact.get('source_tier')}) | Kanıt zamanı: {evidence_at}"
                )
                corroborators = fact.get("corroborating_sources") or []
                if corroborators:
                    corr_text = ", ".join(
                        f"{_source_label(item.get('source'))}/Tier {item.get('source_tier')}"
                        for item in corroborators
                        if isinstance(item, dict)
                    )
                    if corr_text:
                        text.append(f"     İKİNCİ DOĞRULAMA: {corr_text}")
            else:
                derived = ", ".join(str(x) for x in fact.get("derived_from_fact_ids") or []) or "—"
                text.append(
                    f"  {idx}. [{fact_id}] ÇIKARIM | {category_tr.get(category, category)} | {relation_tr.get(relationship, relationship)} | "
                    f"{fact.get('claim')} | Dayanak FACT: {derived}"
                )

        for check_name, label in (("squad", "KADRO KONTROLÜ"), ("performance", "PERFORMANS KONTROLÜ"), ("counter", "KARŞI TEZ KONTROLÜ")):
            check = checks.get(check_name) if isinstance(checks.get(check_name), dict) else {}
            status = str(check.get("status") or "").upper()
            ids = ", ".join(str(x) for x in check.get("fact_ids") or []) or "—"
            text.append(f"{label}: {status_tr.get(status, status)} | Kanıt: {ids} | {check.get('note') or ''}")

        text.extend(
            [
                f"ARAŞTIRMA DESTEĞİ: {row['research_support']} (FACT: {', '.join(row['support_fact_ids']) or '—'})",
                f"EN GÜÇLÜ ÇELİŞKİ: {row['research_counter']} (FACT: {', '.join(row['counter_fact_ids']) or '—'})",
                f"ÖNEMLİ EKSİK: {row['important_absence'] or 'Yok / material değil'}",
                f"ARAŞTIRMA KAPSAMI: {coverage_tr.get(coverage, coverage)}",
                f"ARAŞTIRMA NE DİYOR: {row['research_synthesis']}",
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
