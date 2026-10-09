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


def _num(value: Any, *, digits: int = 2) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return f"{float(value):,.{digits}f}"


def _money(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return f"${float(value):,.2f}"


def _point_text(point: Any) -> str:
    if not isinstance(point, dict):
        return "—"
    return (
        f"oran {_num(point.get('odds'))} | pay %{_num(point.get('share'))} | "
        f"para {_money(point.get('amount'))} | hacim {_money(point.get('volume'))} | "
        f"{point.get('observed_at') or 'zaman yok'}"
    )


def _delta_text(metrics: Any) -> str:
    if not isinstance(metrics, dict):
        return "—"
    return (
        f"oran Δ {_num(metrics.get('odds_delta'), digits=3)} ({_num(metrics.get('odds_delta_pct'))}%) | "
        f"olasılık Δ {_num(metrics.get('implied_probability_delta_pp'))} puan | "
        f"pay Δ {_num(metrics.get('share_delta_pp'))} puan | "
        f"para Δ {_money(metrics.get('amount_delta'))} ({_num(metrics.get('amount_delta_pct'))}%) | "
        f"para hızı {_money(metrics.get('amount_velocity_per_hour'))}/saat"
    )


def _quant_text(metrics: Any) -> str:
    if not isinstance(metrics, list) or not metrics:
        return "—"
    rows: list[str] = []
    for item in metrics:
        if not isinstance(item, dict):
            continue
        rows.append(
            f"{item.get('metric')}: {_num(item.get('value'))} {item.get('unit') or ''} ({item.get('sample') or 'örneklem yok'})"
        )
    return "; ".join(rows) or "—"


def _stage1_evidence_summary(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return "SXF kanıt paketi yok"
    selected = evidence.get("selected_selection") if isinstance(evidence.get("selected_selection"), dict) else {}
    return (
        f"Açılış [{_point_text(selected.get('first'))}] → Son [{_point_text(selected.get('last'))}] | "
        f"{_delta_text(selected.get('open_to_latest'))}"
    )


def render_stage1(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    text: list[str] = ["STAGE 1 — SXF ADAYLARI VE KULLANILAN KANIT"]
    by_id = {
        str(item.get("fixture_id") or item.get("fixture_uid") or item.get("match_id_hash") or ""): item
        for item in payload.get("screening_results") or []
        if isinstance(item, dict)
    }
    window_labels = {
        "h24": "24 SAAT",
        "h12": "12 SAAT",
        "h6": "6 SAAT",
        "h3": "3 SAAT",
        "h1": "1 SAAT",
        "m30": "30 DK",
        "m15": "15 DK",
    }
    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or "")
        pref = match.get("preference") or {}
        screening = by_id.get(fixture_id, {})
        evidence = match.get("sxf_evidence") if isinstance(match.get("sxf_evidence"), dict) else {}
        selected = evidence.get("selected_selection") if isinstance(evidence.get("selected_selection"), dict) else {}
        row = {
            "fixture_id": fixture_id,
            "preference": pref,
            "attention_signals": list(screening.get("attention_signals") or []),
            "rationale": match.get("rationale"),
            "strongest_counterargument": match.get("strongest_counterargument"),
            "sxf_evidence": evidence,
        }
        rows.append(row)
        text.extend(
            [
                "",
                f"{fixture_id}",
                f"SXF TERCİHİ: {pref.get('selection')} | {pref.get('market')}{_price_text(pref)}",
                f"DİKKAT SİNYALLERİ: {', '.join(row['attention_signals']) or '—'}",
                "KULLANILAN HAM SXF VERİSİ:",
                f"  AÇILIŞ/İLK: {_point_text(selected.get('first'))}",
                f"  SON: {_point_text(selected.get('last'))}",
                f"  AÇILIŞ → SON DEĞİŞİM: {_delta_text(selected.get('open_to_latest'))}",
                f"  TARİHÇE: {selected.get('history_count', 0)} gözlem | reversal segmenti {selected.get('reversal_segments', 0)} | son veri yaşı {selected.get('latest_age_seconds', 0)} sn",
            ]
        )
        windows = selected.get("windows") if isinstance(selected.get("windows"), dict) else {}
        for key in ("h24", "h12", "h6", "h3", "h1", "m30", "m15"):
            item = windows.get(key)
            if not isinstance(item, dict):
                continue
            text.append(f"  {window_labels[key]} → SON: {_delta_text(item.get('metrics'))}")

        market_rows = evidence.get("market_comparison") if isinstance(evidence.get("market_comparison"), list) else []
        if market_rows:
            text.append("AYNI MARKETTE SON DURUM:")
            for item in market_rows:
                if not isinstance(item, dict):
                    continue
                text.append(f"  {item.get('selection')}: {_point_text(item.get('last'))}")

        cross_rows = evidence.get("cross_market_snapshot") if isinstance(evidence.get("cross_market_snapshot"), list) else []
        if cross_rows:
            text.append("NATIVE CROSS-MARKET SON DURUM:")
            for item in cross_rows:
                if not isinstance(item, dict):
                    continue
                text.append(f"  {item.get('market')} / {item.get('selection')}: {_point_text(item.get('last'))}")

        text.extend(
            [
                f"ANALİZ GEREKÇESİ: {row['rationale']}",
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
    relation_tr = {"SUPPORTS": "DESTEKLİYOR", "CONTRADICTS": "ÇELİŞİYOR", "NEUTRAL": "NÖTR", "UNKNOWN": "BİLİNMİYOR"}
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
    materiality_tr = {"CRITICAL": "KRİTİK", "MATERIAL": "ÖNEMLİ", "CONTEXT": "BAĞLAMSAL"}
    importance_tr = {
        "NONE": "YOK",
        "LOW": "DÜŞÜK",
        "MEDIUM": "ORTA",
        "HIGH": "YÜKSEK",
        "CRITICAL": "KRİTİK",
        "UNKNOWN": "BİLİNMİYOR",
    }

    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or "")
        frozen = match.get("frozen_stage1_preference") or {}
        frozen_evidence = match.get("frozen_stage1_evidence")
        coverage = str(match.get("coverage") or "").upper()
        verdict = str(match.get("verdict") or "").upper()
        facts = match.get("facts") or []
        checks = match.get("research_checks") if isinstance(match.get("research_checks"), dict) else {}
        absence = match.get("absence_assessment") if isinstance(match.get("absence_assessment"), dict) else {}
        row = {
            "fixture_id": fixture_id,
            "frozen_stage1_preference": frozen,
            "frozen_stage1_evidence": frozen_evidence,
            "research_support": match.get("research_support"),
            "research_counter": match.get("research_counter"),
            "research_synthesis": match.get("research_synthesis"),
            "important_absence": match.get("important_absence"),
            "absence_assessment": absence,
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
                f"STAGE 1 SAYISAL REFERANSI: {_stage1_evidence_summary(frozen_evidence)}",
                "ARAŞTIRMADA KULLANILAN KANITLAR:",
            ]
        )
        for idx, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                continue
            kind = str(fact.get("kind") or "").upper()
            relationship = str(fact.get("relationship") or "").upper()
            category = str(fact.get("category") or "").upper()
            materiality = str(fact.get("materiality") or "").upper()
            fact_id = str(fact.get("fact_id") or f"fact-{idx}")
            if kind == "FACT":
                evidence_at = str(fact.get("evidence_at") or "")
                text.append(
                    f"  {idx}. [{fact_id}] {category_tr.get(category, category)} | {relation_tr.get(relationship, relationship)} | "
                    f"ÖNEM {materiality_tr.get(materiality, materiality)} | {fact.get('claim')}"
                )
                text.append(f"     NEDEN ÖNEMLİ: {fact.get('importance_reason') or '—'}")
                text.append(f"     SAYISAL BAĞLAM: {_quant_text(fact.get('quantitative_context'))}")
                text.append(
                    f"     KAYNAK: {_source_label(fact.get('source'))} (Tier {fact.get('source_tier')}) | Kanıt zamanı: {evidence_at} | Gözlem: {fact.get('observed_at') or '—'}"
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
                    f"ÖNEM {materiality_tr.get(materiality, materiality)} | {fact.get('claim')} | Dayanak FACT: {derived}"
                )
                text.append(f"     NEDEN ÖNEMLİ: {fact.get('importance_reason') or '—'}")

        for check_name, label in (("squad", "KADRO KONTROLÜ"), ("performance", "PERFORMANS KONTROLÜ"), ("counter", "KARŞI TEZ KONTROLÜ")):
            check = checks.get(check_name) if isinstance(checks.get(check_name), dict) else {}
            status = str(check.get("status") or "").upper()
            ids = ", ".join(str(x) for x in check.get("fact_ids") or []) or "—"
            text.append(f"{label}: {status_tr.get(status, status)} | Kanıt: {ids} | {check.get('note') or ''}")

        absence_status = str(absence.get("status") or "").upper()
        text.append("EKSİK / KADRO ETKİ DEĞERLENDİRMESİ:")
        if absence_status == "IDENTIFIED":
            text.extend(
                [
                    f"  OYUNCU/BİRİM: {absence.get('subject')} | ROL: {absence.get('role')}",
                    f"  DURUM: {absence.get('availability')} | ÖNEM: {importance_tr.get(str(absence.get('importance') or '').upper(), absence.get('importance'))}",
                    f"  STAGE 1 TEZİNE ETKİ: {relation_tr.get(str(absence.get('thesis_effect') or '').upper(), absence.get('thesis_effect'))}",
                    f"  NEDEN BU KADAR ÖNEMLİ: {absence.get('importance_reason')}",
                    f"  SAYISAL ROL/KATKI: {_quant_text(absence.get('quantified_context'))}",
                    f"  DAYANAK FACT: {', '.join(str(x) for x in absence.get('fact_ids') or []) or '—'}",
                ]
            )
        elif absence_status == "NONE":
            text.append(f"  MATERIAL EKSİK YOK | Gerekçe: {absence.get('importance_reason') or '—'}")
        else:
            text.append(f"  BİLİNMİYOR | Gerekçe: {absence.get('importance_reason') or 'yeterli güvenilir veri yok'}")

        text.extend(
            [
                f"ARAŞTIRMA DESTEĞİ: {row['research_support']} (FACT: {', '.join(row['support_fact_ids']) or '—'})",
                f"EN GÜÇLÜ ÇELİŞKİ: {row['research_counter']} (FACT: {', '.join(row['counter_fact_ids']) or '—'})",
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
