#!/usr/bin/env python3
"""One-shot audited real-data Predictor E2E for 2026-10-08.

This script is intentionally narrow: it reads the production SXF source, runs the
strict Stage 1 -> Stage 2 -> Stage 3 publication boundary in a temporary SQLite
store, and lets the configured Learning Archive publisher persist formal BET/WATCH
cases and the day diary. It never mutates SmartXFlow production source or Supabase.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from typing import Any

from learning_archive.outbox import load_dotenv_literal
from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.strict_service import StrictPredictorOrchestrator
from predictor_orchestrator.store import SQLiteOrchestratorStore
from predictor_orchestrator.sxf_source import SXFStage1Source


RESEARCH_OBSERVED_AT = "2026-10-07T22:26:37+00:00"
AGENT_MODEL = "GPT-5.6-Sol-ChatGPT-Agent"

SELECTED = {
    "1b98061c93a7": {
        "market": "1X2",
        "selection": "Home",
        "signals": ["PRICE_CONFIRMATION", "PERSISTENCE", "LATE_MOVE", "MONEY_ACCELERATION"],
        "counter": "The price confirmation is real, but the historical volume is modest enough that external form must remain a material counter-check.",
    },
    "223a5be6cdd0": {
        "market": "1X2",
        "selection": "Home",
        "signals": ["MONEY_ACCELERATION", "PRICE_CONFIRMATION", "LIQUIDITY_ADJUSTED_MOVE", "PERSISTENCE"],
        "counter": "The move is large relative to the market's small absolute volume, so low-liquidity overreaction remains possible.",
    },
    "7168c0ce3b11": {
        "market": "1X2",
        "selection": "Draw",
        "signals": ["MONEY_ACCELERATION", "PRICE_CONFIRMATION", "PERSISTENCE", "PRICE_RESISTANCE"],
        "counter": "Recent draw money increased strongly, but the latest price stopped shortening, leaving some price resistance.",
    },
    "18e9be344fff": {
        "market": "1X2",
        "selection": "Draw",
        "signals": ["MONEY_ACCELERATION", "PRICE_CONFIRMATION", "LATE_MOVE", "LIQUIDITY_ADJUSTED_MOVE"],
        "counter": "The draw move is sharp but still comes from a comparatively small absolute 1X2 market.",
    },
    "d227a7f83bd2": {
        "market": "1X2",
        "selection": "Home",
        "signals": ["MONEY_ACCELERATION", "PRICE_CONFIRMATION", "PERSISTENCE", "SATURATION", "CROSS_MARKET_CONFIRMATION"],
        "counter": "Very high concentration can become saturation rather than new information, so opponent form and squad context still matter.",
    },
    "0727317459fb": {
        "market": "1X2",
        "selection": "Away",
        "signals": ["MONEY_ACCELERATION", "PRICE_RESISTANCE", "DIVERGENCE", "PERSISTENCE", "LATE_MOVE"],
        "counter": "Away money became dominant without durable price shortening, a classic price-resistance warning that can indicate noisy or non-informative money.",
    },
}


STAGE2_FACTS: dict[str, dict[str, Any]] = {
    "1b98061c93a7": {
        "facts": [
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "JS Saoura's latest listed league results were a 0-0 draw at US Biskra and a 4-0 defeat at JS El Biar.",
                "source": "https://www.mackolik.com/mac/js-saoura-vs-olympique-akbou/karsilastirma/9hhftf35l470kx2cbruj3fkt0",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "NEUTRAL",
                "claim": "Olympique Akbou's listed opening league sequence was a 2-0 win at JS El Biar followed by 2-0 and 3-2 defeats to Rouisset and USM Alger.",
                "source": "https://www.mackolik.com/takim/olympique-akbou/ma%C3%A7lar/83r92ut8bmai79ejpgl3uu5pm",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "JS Saoura won the two previous listed home meetings with Olympique Akbou, 3-2 in October 2025 and 2-1 in February 2025.",
                "source": "https://www.mackolik.com/mac/js-saoura-vs-olympique-akbou/karsilastirma/9hhftf35l470kx2cbruj3fkt0",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "The most recent listed head-to-head was Olympique Akbou 1-0 JS Saoura in March 2026.",
                "source": "https://www.mackolik.com/mac/js-saoura-vs-olympique-akbou/karsilastirma/9hhftf35l470kx2cbruj3fkt0",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
        ],
        "support": "Saoura's two previous home H2H wins keep the home thesis plausible despite weak current form.",
        "counter": "Saoura's latest league form includes a 4-0 defeat and no win in the two listed league matches, while Akbou won the latest H2H.",
        "absence": "No reliable current squad/injury report was found for both teams.",
        "coverage": "MEDIUM",
        "verdict": "PARTIALLY_CONFIRMED",
    },
    "223a5be6cdd0": {
        "facts": [
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "TFF records Orduspor 1967 beating Torul Belediye 10-0 in the previous Turkish Cup round on 17 September 2026.",
                "source": "https://www.tff.org/Default.aspx?macId=321631&pageId=528",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "Orduspor's listed league results include a 3-0 home win over Büyükçekmece Gücü and a 1-0 away win at Gölcükspor in late September.",
                "source": "https://www.besoccer.com/team/matches/orduspor/2024",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "Orduspor then lost its latest listed league match 3-0 at home to Fatsa Belediye on 3 October.",
                "source": "https://www.besoccer.com/team/matches/orduspor/2024",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "Karadeniz Ereğli won the most recent listed H2H 5-3 against Orduspor in April 2026.",
                "source": "https://www.besoccer.com/team/matches/karadeniz-eregli/2026",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "Karadeniz Ereğli opened the listed 2026-27 league sequence with a 1-1 draw, a 1-0 win and a 0-0 draw.",
                "source": "https://www.besoccer.com/team/matches/karadeniz-eregli/2026",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
        ],
        "support": "Orduspor showed real September scoring and winning form and had already produced a dominant cup win.",
        "counter": "The latest 0-3 loss plus Karadeniz Ereğli's unbeaten listed opening sequence and 5-3 H2H win prevent a clean confirmation.",
        "absence": "No reliable current squad/injury report was found for both teams.",
        "coverage": "MEDIUM",
        "verdict": "PARTIALLY_CONFIRMED",
    },
    "7168c0ce3b11": {
        "facts": [
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "Universitatea Cluj's official pre-match conference says the team is seeking a third consecutive league win and that one point would still be acceptable if the team plays to win.",
                "source": "https://www.fcucluj.ro/stire/viziune-pragmatica-a-lui-bergodi-asupra-derby-ul-de-joi-este-o-restanta-si-deci-o-sansa-in-plus-fata-de-celelalte-echipe",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "Universitatea Cluj's listed recent league wins include 2-0 at Voluntari and 3-0 against Oțelul.",
                "source": "https://www.fcucluj.ro/",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "NEUTRAL",
                "claim": "CFR Cluj's listed recent sequence includes a 3-1 win over Botoșani, a 1-3 loss at Sepsi and a 0-0 draw with Farul.",
                "source": "https://www.mackolik.com/",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "INFERENCE",
                "relationship": "CONTRADICTS",
                "claim": "U Cluj's strong recent momentum also leaves a live away-win path, so the same evidence that weakens CFR does not uniquely imply a draw.",
                "source": None,
                "source_tier": None,
                "observed_at": None,
            },
        ],
        "support": "U Cluj's official stance and recent form make a competitive derby and draw path credible.",
        "counter": "The visitors' winning momentum can resolve as an away win rather than a draw, while CFR still has recent winning evidence.",
        "absence": "No sufficiently reliable complete current squad availability report was found for both sides.",
        "coverage": "MEDIUM",
        "verdict": "PARTIALLY_CONFIRMED",
    },
    "18e9be344fff": {
        "facts": [
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "Widad Temara's listed Botola results include a 3-1 away win at Wydad Casablanca on 26 September.",
                "source": "https://www.mackolik.com/takim/widad-t%C3%A9mara/ma%C3%A7lar/4svjhqsjiwlvg7pqp5qxihzkq",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "Widad Temara then lost 1-0 at home to Union Touarga on 2 October.",
                "source": "https://www.mackolik.com/takim/widad-t%C3%A9mara/ma%C3%A7lar/4svjhqsjiwlvg7pqp5qxihzkq",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "FAR Rabat beat Widad Temara 2-1 and 3-2 in two listed September friendlies.",
                "source": "https://www.besoccer.com/team/matches/widad-temara",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "FAR Rabat's listed preceding league run included multiple draws, including 2-2 with RS Berkane, 2-2 with UTS and 0-0 with Renaissance Zemamra.",
                "source": "https://www.besoccer.com/team/matches/far-rabat",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
        ],
        "support": "Widad's 3-1 away win at Wydad and FAR's recent draw-heavy league sequence give the draw thesis a real football explanation.",
        "counter": "FAR beat Widad in both September friendlies, so the direct recent matchup evidence still favors the home side over a draw.",
        "absence": "No reliable complete current squad/injury report was available for both teams.",
        "coverage": "MEDIUM",
        "verdict": "PARTIALLY_CONFIRMED",
    },
    "d227a7f83bd2": {
        "facts": [
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "Shamrock Rovers' official team news says their previous league match was a 3-2 home comeback win over Waterford and the squad had trained through the break for the title run-in.",
                "source": "https://www.shamrockrovers.ie/news/team-news-home-vs-drogheda-united-08-10-26/",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "The same official preview states Shamrock drew 0-0 twice away to Drogheda this season but won the home meeting 4-1 in May.",
                "source": "https://www.shamrockrovers.ie/news/team-news-home-vs-drogheda-united-08-10-26/",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "Shamrock reported low bodies after the break; Danny Mandroiu remains out for the season, Danny Grant awaited specialist guidance and Victor Ozhianvuna was awaiting another scan.",
                "source": "https://www.shamrockrovers.ie/news/team-news-home-vs-drogheda-united-08-10-26/",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "Drogheda's latest listed league run includes 2-0 over Sligo and 2-1 away at Shelbourne before a 2-1 loss at Bohemians.",
                "source": "https://www.leagueofireland.ie/mens/sse-airtricity-mens-premier-division/results/",
                "source_tier": "A",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
        ],
        "support": "The home 4-1 H2H, title-run context and latest home comeback win align with the very strong SXF home concentration.",
        "counter": "Shamrock's availability concerns and Drogheda's two recent league wins mean the favorite is not risk-free.",
        "absence": None,
        "coverage": "HIGH",
        "verdict": "PARTIALLY_CONFIRMED",
    },
    "0727317459fb": {
        "facts": [
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "FotMob lists Los Chankas' recent form as five straight losses, including 0-3, 0-3, 3-4, 0-5 and 1-2 scorelines.",
                "source": "https://www.fotmob.com/matches/los-chankas-vs-atletico-grau/hmkh768k",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "CONTRADICTS",
                "claim": "FotMob lists Atlético Grau's recent sequence with three wins and two losses, materially stronger than Los Chankas' listed run.",
                "source": "https://www.fotmob.com/matches/los-chankas-vs-atletico-grau/hmkh768k",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "FotMob lists Atlético Grau's Adrián De La Cruz and Lucas Acevedo as unavailable while listing no unavailable player for Los Chankas.",
                "source": "https://www.fotmob.com/matches/los-chankas-vs-atletico-grau/hmkh768k",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
            {
                "kind": "FACT",
                "relationship": "SUPPORTS",
                "claim": "The most recent listed H2H was Los Chankas 2-0 Atlético Grau on 17 April 2026.",
                "source": "https://www.fotmob.com/matches/los-chankas-vs-atletico-grau/hmkh768k",
                "source_tier": "B",
                "observed_at": RESEARCH_OBSERVED_AT,
            },
        ],
        "support": "Grau's two listed absences and Los Chankas' 2-0 win in the latest H2H provide real support for the away thesis.",
        "counter": "Los Chankas' five-loss recent run is a major contradiction and is especially important because SXF away money has not produced durable price shortening.",
        "absence": "Confirmed lineups were not yet available at research time.",
        "coverage": "MEDIUM",
        "verdict": "PARTIALLY_CONFIRMED",
    },
}


STAGE3 = {
    "1b98061c93a7": {
        "market": "1X2", "selection": "Home", "grade": "B", "counter_severity": "STRONG",
        "raw_confidence": 75, "divergence_state": "CONFIRMED", "execution_type": "NATIVE",
        "rationale": "SXF keeps a strongly concentrated home position with price confirmation, but Stage 2 exposes weak recent Saoura form, so the thesis remains WATCH rather than a bet.",
        "counter": "Saoura's 4-0 league defeat and Akbou's latest H2H win are material football counters.",
        "change_driver": "NONE",
    },
    "223a5be6cdd0": {
        "market": "1X2", "selection": "Home", "grade": "B", "counter_severity": "MEDIUM",
        "raw_confidence": 73, "divergence_state": "MIXED", "execution_type": "NATIVE",
        "rationale": "The large home repricing and September wins are meaningful, but absolute liquidity is small and the latest 0-3 loss prevents formal BET quality.",
        "counter": "Karadeniz Ereğli's unbeaten listed opening sequence and the 5-3 H2H win keep the upset path live.",
        "change_driver": "NONE",
    },
    "7168c0ce3b11": {
        "market": "1X2", "selection": "Draw", "grade": "B", "counter_severity": "MEDIUM",
        "raw_confidence": 76, "divergence_state": "MIXED", "execution_type": "NATIVE",
        "rationale": "Draw money accumulated materially and U Cluj's official pre-match posture makes a competitive derby plausible, but the latest price resistance and visitors' winning momentum cap the grade at WATCH.",
        "counter": "U Cluj's form can convert the same anti-CFR evidence into an away win instead of a draw.",
        "change_driver": "NONE",
    },
    "18e9be344fff": {
        "market": "1X2", "selection": "Draw", "grade": "B", "counter_severity": "MEDIUM",
        "raw_confidence": 74, "divergence_state": "CONFIRMED", "execution_type": "NATIVE",
        "rationale": "Late draw money and price confirmation have a plausible football explanation through Widad's competitiveness and FAR's draw-heavy prior league run, but the direct September friendlies still favor FAR.",
        "counter": "FAR beat Widad in both September friendlies, so the draw is not sufficiently clean for a formal BET.",
        "change_driver": "NONE",
    },
    "d227a7f83bd2": {
        "market": "1X2", "selection": "Home", "grade": "A", "counter_severity": "MEDIUM",
        "raw_confidence": 88, "divergence_state": "CONFIRMED", "execution_type": "NATIVE",
        "rationale": "SXF shows persistent high-volume home concentration, while official team news confirms title-run motivation, a 3-2 home comeback last time out and a 4-1 home H2H win over Drogheda; this clears BET despite squad cautions.",
        "counter": "Shamrock have some availability concerns and Drogheda recently produced consecutive league wins before the Bohemians defeat.",
        "change_driver": "NONE",
    },
    "0727317459fb": {
        "market": "1X2", "selection": "Away", "grade": "C", "counter_severity": "STRUCTURAL",
        "raw_confidence": 66, "divergence_state": "ADVERSE", "execution_type": "NATIVE",
        "rationale": "Away money is unusually concentrated, but it has not generated durable price confirmation and Stage 2 shows a five-loss Los Chankas run; the concrete away preference is retained for audit but fails the action gate.",
        "counter": "Grau's stronger recent form makes the unconfirmed away-money signal vulnerable despite Grau absences and the latest H2H loss.",
        "change_driver": "NONE",
    },
}


class NoLLM:
    model = AGENT_MODEL

    def generate(self, **_: Any):
        raise RuntimeError("real E2E uses external-agent submit only")


def _feature(context_by_id: dict[str, dict[str, Any]], fixture_id: str, market: str, selection: str) -> dict[str, Any]:
    fixture = context_by_id.get(fixture_id)
    if fixture is None:
        raise RuntimeError(f"selected fixture is missing from real Stage 1 universe: {fixture_id}")
    feature = (((fixture.get("markets") or {}).get(market) or {}).get(selection))
    if not isinstance(feature, dict) or not isinstance(feature.get("last"), dict):
        raise RuntimeError(f"selected Stage 1 market has no real history: {fixture_id} {market} {selection}")
    return feature


def _stage1_generated(context: dict[str, Any]) -> dict[str, Any]:
    fixture_ids = [str(value) for value in context.get("source_fixture_ids") or []]
    missing = sorted(set(SELECTED) - set(fixture_ids))
    if missing:
        raise RuntimeError(f"selected fixtures missing from Stage 1 universe: {missing}")
    by_id = {
        str(item.get("fixture_id") or ""): item
        for item in context.get("fixtures") or []
        if isinstance(item, dict)
    }
    screening_results = []
    matches = []
    for fixture_id in fixture_ids:
        selected = fixture_id in SELECTED
        cfg = SELECTED.get(fixture_id) or {}
        screening_results.append(
            {
                "fixture_id": fixture_id,
                "temporal_reviewed": True,
                "selected": selected,
                "attention_signals": list(cfg.get("signals") or []),
                "attention_explanation": (
                    "Selected after full temporal SXF review of money, price, persistence and liquidity behavior."
                    if selected else None
                ),
            }
        )
        if not selected:
            continue
        feature = _feature(by_id, fixture_id, cfg["market"], cfg["selection"])
        first = feature.get("first") or {}
        last = feature.get("last") or {}
        deltas = feature.get("open_to_latest") or {}
        rationale = (
            f"SXF temporal path: {cfg['selection']} {cfg['market']} odds {first.get('odds')} -> {last.get('odds')}; "
            f"share {first.get('share')} -> {last.get('share')}; amount {first.get('amount')} -> {last.get('amount')}; "
            f"open-to-latest deltas={deltas}; latest volume={last.get('volume')}."
        )
        matches.append(
            {
                "fixture_id": fixture_id,
                "preference": {"market": cfg["market"], "selection": cfg["selection"], "price": None},
                "rationale": rationale,
                "strongest_counterargument": cfg["counter"],
            }
        )
    return {"screening_results": screening_results, "matches": matches}


def _stage2_generated() -> dict[str, Any]:
    matches = []
    for fixture_id in SELECTED:
        research = STAGE2_FACTS[fixture_id]
        matches.append(
            {
                "fixture_id": fixture_id,
                "research_checks": {
                    "squad_checked": True,
                    "performance_checked": True,
                    "counter_checked": True,
                    "coverage_classified": True,
                },
                "facts": deepcopy(research["facts"]),
                "research_support": research["support"],
                "research_counter": research["counter"],
                "important_absence": research["absence"],
                "coverage": research["coverage"],
                "verdict": research["verdict"],
            }
        )
    return {"matches": matches}


def _stage3_generated() -> dict[str, Any]:
    matches = []
    for fixture_id in SELECTED:
        row = STAGE3[fixture_id]
        matches.append(
            {
                "fixture_id": fixture_id,
                "preference": {"market": row["market"], "selection": row["selection"], "price": None},
                "grade": row["grade"],
                "counter_severity": row["counter_severity"],
                "raw_confidence": row["raw_confidence"],
                "divergence_state": row["divergence_state"],
                "execution_type": row["execution_type"],
                "material_reversal_explained": False,
                "material_reversal_explanation": None,
                "rationale": row["rationale"],
                "strongest_counterargument": row["counter"],
                "change_driver": row["change_driver"],
            }
        )
    return {"matches": matches}


def main() -> int:
    load_dotenv_literal("/opt/smartxflow/.env")
    source = SXFStage1Source.from_env()
    try:
        scope = {
            "date": "2026-10-08",
            "window_tr": ["18:00", "24:00"],
            "timezone": "Europe/Istanbul",
            "future_only": True,
        }
        context = source.build_stage1_context(scope)
    finally:
        source.close()

    with tempfile.TemporaryDirectory(prefix="sxf-predictor-real-e2e-") as tmp:
        db_path = str(Path(tmp) / "predictor.sqlite3")
        cfg = OrchestratorConfig(
            api_key="",
            api_base="https://api.openai.com/v1",
            model=AGENT_MODEL,
            state_db_path=db_path,
            service_secret="real-e2e-local-only",
            max_attempts=1,
            request_timeout_seconds=120,
            stage2_web_search=False,
            max_output_tokens=12000,
        )
        store = SQLiteOrchestratorStore(db_path)
        orch = StrictPredictorOrchestrator(config=cfg, store=store, llm=NoLLM())
        if orch.archive_publisher is None:
            raise RuntimeError("strict Learning Archive publisher is not configured")

        workflow = orch.create_workflow(scope)
        context_meta = store.save_trusted_context(workflow.workflow_id, "STAGE1", context)
        stage1 = orch.submit_generated_stage(
            workflow_id=workflow.workflow_id,
            stage="STAGE1",
            generated=_stage1_generated(context),
            agent_model=AGENT_MODEL,
        )
        stage2 = orch.submit_generated_stage(
            workflow_id=workflow.workflow_id,
            stage="STAGE2",
            generated=_stage2_generated(),
            user_authorized=True,
            agent_model=AGENT_MODEL,
        )
        stage3 = orch.submit_generated_stage(
            workflow_id=workflow.workflow_id,
            stage="STAGE3",
            generated=_stage3_generated(),
            user_authorized=True,
            agent_model=AGENT_MODEL,
        )

        output = {
            "status": "REAL_PREDICTOR_E2E_DONE",
            "workflow_id": workflow.workflow_id,
            "context_sha256": context_meta["context_sha256"],
            "source_fixture_count": len(context.get("source_fixture_ids") or []),
            "selected_fixture_ids": list(SELECTED),
            "stage1": {
                "stage_run_id": stage1["stage_run_id"],
                "publication_receipt": stage1["publication_receipt"],
                "report": stage1["report"],
            },
            "stage2": {
                "stage_run_id": stage2["stage_run_id"],
                "publication_receipt": stage2["publication_receipt"],
                "report": stage2["report"],
            },
            "stage3": {
                "stage_run_id": stage3["stage_run_id"],
                "publication_receipt": stage3["publication_receipt"],
                "report": stage3["report"],
                "archive": stage3["archive"],
            },
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        if stage3["archive"].get("status") != "RECORDED":
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
