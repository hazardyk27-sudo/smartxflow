from __future__ import annotations

from copy import deepcopy
from typing import Any


_STRING_OR_NULL = {"type": ["string", "null"]}
_NUMBER_OR_NULL = {"type": ["number", "null"]}


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


PREFERENCE_SCHEMA = _object(
    {
        "market": {"type": "string", "minLength": 1},
        "selection": {"type": "string", "minLength": 1},
        "price": _NUMBER_OR_NULL,
    },
    ["market", "selection", "price"],
)

STAGE1_OUTPUT_SCHEMA = _object(
    {
        "screening_results": {
            "type": "array",
            "items": _object(
                {
                    "fixture_id": {"type": "string", "minLength": 1},
                    "temporal_reviewed": {"type": "boolean"},
                    "selected": {"type": "boolean"},
                    "attention_signals": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "MONEY_ACCELERATION",
                                "PRICE_CONFIRMATION",
                                "PRICE_RESISTANCE",
                                "DIVERGENCE",
                                "REVERSAL",
                                "PERSISTENCE",
                                "LIQUIDITY_ADJUSTED_MOVE",
                                "CROSS_MARKET_CONFIRMATION",
                                "CROSS_MARKET_CONFLICT",
                                "LATE_MOVE",
                                "SATURATION",
                                "OTHER",
                            ],
                        },
                    },
                    "attention_explanation": _STRING_OR_NULL,
                },
                [
                    "fixture_id",
                    "temporal_reviewed",
                    "selected",
                    "attention_signals",
                    "attention_explanation",
                ],
            ),
        },
        "matches": {
            "type": "array",
            "items": _object(
                {
                    "fixture_id": {"type": "string", "minLength": 1},
                    "preference": deepcopy(PREFERENCE_SCHEMA),
                    "rationale": {"type": "string", "minLength": 1},
                    "strongest_counterargument": {"type": "string", "minLength": 1},
                },
                ["fixture_id", "preference", "rationale", "strongest_counterargument"],
            ),
        },
    },
    ["screening_results", "matches"],
)

STAGE2_CORROBORATING_SOURCE_SCHEMA = _object(
    {
        "source": {"type": "string", "minLength": 1},
        "source_tier": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "observed_at": {"type": "string", "minLength": 1},
        "evidence_at": {"type": "string", "minLength": 1},
    },
    ["source", "source_tier", "observed_at", "evidence_at"],
)

STAGE2_QUANT_METRIC_SCHEMA = _object(
    {
        "metric": {"type": "string", "minLength": 1},
        "value": {"type": "number"},
        "unit": {"type": "string", "minLength": 1},
        "sample": {"type": "string", "minLength": 1},
    },
    ["metric", "value", "unit", "sample"],
)

STAGE2_FACT_SCHEMA = _object(
    {
        "fact_id": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": ["FACT", "INFERENCE"]},
        "category": {
            "type": "string",
            "enum": ["SQUAD", "LINEUP", "MANAGER_COMMENT", "PERFORMANCE", "TACTICAL", "CONTEXT", "H2H"],
        },
        "materiality": {"type": "string", "enum": ["CRITICAL", "MATERIAL", "CONTEXT"]},
        "relationship": {"type": "string", "enum": ["SUPPORTS", "CONTRADICTS", "NEUTRAL"]},
        "claim": {"type": "string", "minLength": 1},
        "importance_reason": {"type": "string", "minLength": 1},
        "quantitative_context": {
            "type": "array",
            "maxItems": 4,
            "items": deepcopy(STAGE2_QUANT_METRIC_SCHEMA),
        },
        "source": _STRING_OR_NULL,
        "source_tier": {"type": ["string", "null"], "enum": ["A", "B", "C", "D", None]},
        "observed_at": _STRING_OR_NULL,
        "evidence_at": _STRING_OR_NULL,
        "derived_from_fact_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "corroborating_sources": {
            "type": "array",
            "maxItems": 3,
            "items": deepcopy(STAGE2_CORROBORATING_SOURCE_SCHEMA),
        },
    },
    [
        "fact_id",
        "kind",
        "category",
        "materiality",
        "relationship",
        "claim",
        "importance_reason",
        "quantitative_context",
        "source",
        "source_tier",
        "observed_at",
        "evidence_at",
        "derived_from_fact_ids",
        "corroborating_sources",
    ],
)

STAGE2_CHECK_SCHEMA = _object(
    {
        "status": {"type": "string", "enum": ["VERIFIED", "UNKNOWN"]},
        "fact_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "note": {"type": "string", "minLength": 1},
    },
    ["status", "fact_ids", "note"],
)

STAGE2_ABSENCE_ASSESSMENT_SCHEMA = _object(
    {
        "status": {"type": "string", "enum": ["NONE", "UNKNOWN", "IDENTIFIED"]},
        "subject": _STRING_OR_NULL,
        "role": _STRING_OR_NULL,
        "availability": {
            "type": "string",
            "enum": ["NONE", "OUT", "DOUBTFUL", "SUSPENDED", "ROTATION_RISK", "UNKNOWN"],
        },
        "importance": {
            "type": "string",
            "enum": ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"],
        },
        "thesis_effect": {"type": "string", "enum": ["SUPPORTS", "CONTRADICTS", "NEUTRAL", "UNKNOWN"]},
        "importance_reason": {"type": "string", "minLength": 1},
        "fact_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "quantified_context": {
            "type": "array",
            "maxItems": 4,
            "items": deepcopy(STAGE2_QUANT_METRIC_SCHEMA),
        },
    },
    [
        "status",
        "subject",
        "role",
        "availability",
        "importance",
        "thesis_effect",
        "importance_reason",
        "fact_ids",
        "quantified_context",
    ],
)

STAGE2_OUTPUT_SCHEMA = _object(
    {
        "matches": {
            "type": "array",
            "items": _object(
                {
                    "fixture_id": {"type": "string", "minLength": 1},
                    "research_checks": _object(
                        {
                            "squad": deepcopy(STAGE2_CHECK_SCHEMA),
                            "performance": deepcopy(STAGE2_CHECK_SCHEMA),
                            "counter": deepcopy(STAGE2_CHECK_SCHEMA),
                        },
                        ["squad", "performance", "counter"],
                    ),
                    "facts": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 6,
                        "items": deepcopy(STAGE2_FACT_SCHEMA),
                    },
                    "support_fact_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "counter_fact_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "research_support": {"type": "string", "minLength": 1},
                    "research_counter": {"type": "string", "minLength": 1},
                    "research_synthesis": {"type": "string", "minLength": 1},
                    "important_absence": _STRING_OR_NULL,
                    "absence_assessment": deepcopy(STAGE2_ABSENCE_ASSESSMENT_SCHEMA),
                    "coverage": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "verdict": {
                        "type": "string",
                        "enum": ["CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED", "UNEXPLAINED"],
                    },
                },
                [
                    "fixture_id",
                    "research_checks",
                    "facts",
                    "support_fact_ids",
                    "counter_fact_ids",
                    "research_support",
                    "research_counter",
                    "research_synthesis",
                    "important_absence",
                    "absence_assessment",
                    "coverage",
                    "verdict",
                ],
            ),
        }
    },
    ["matches"],
)

STAGE3_OUTPUT_SCHEMA = _object(
    {
        "matches": {
            "type": "array",
            "items": _object(
                {
                    "fixture_id": {"type": "string", "minLength": 1},
                    "preference": deepcopy(PREFERENCE_SCHEMA),
                    "grade": {"type": "string", "enum": ["A+", "A", "B", "C"]},
                    "counter_severity": {
                        "type": "string",
                        "enum": ["NONE", "LIGHT", "MEDIUM", "STRONG", "STRUCTURAL"],
                    },
                    "raw_confidence": {"type": "number", "minimum": 0, "maximum": 100},
                    "divergence_state": {
                        "type": "string",
                        "enum": ["CONFIRMED", "MIXED", "ADVERSE", "MATERIAL_REVERSAL"],
                    },
                    "execution_type": {
                        "type": "string",
                        "enum": ["NATIVE", "PROTECTION", "AGGRESSION"],
                    },
                    "material_reversal_explained": {"type": "boolean"},
                    "material_reversal_explanation": _STRING_OR_NULL,
                    "rationale": {"type": "string", "minLength": 1},
                    "strongest_counterargument": {"type": "string", "minLength": 1},
                    "change_driver": {
                        "type": "string",
                        "enum": ["NONE", "STAGE2_RESEARCH", "EXECUTION_OPTIMIZATION", "MARKET_UPDATE", "BOTH"],
                    },
                },
                [
                    "fixture_id",
                    "preference",
                    "grade",
                    "counter_severity",
                    "raw_confidence",
                    "divergence_state",
                    "execution_type",
                    "material_reversal_explained",
                    "material_reversal_explanation",
                    "rationale",
                    "strongest_counterargument",
                    "change_driver",
                ],
            ),
        }
    },
    ["matches"],
)


_SCHEMAS = {
    "STAGE1": STAGE1_OUTPUT_SCHEMA,
    "STAGE2": STAGE2_OUTPUT_SCHEMA,
    "STAGE3": STAGE3_OUTPUT_SCHEMA,
}


def schema_for_stage(stage: str) -> dict[str, Any]:
    normalized = str(stage or "").upper()
    try:
        return deepcopy(_SCHEMAS[normalized])
    except KeyError as exc:
        raise ValueError(f"unsupported stage: {stage!r}") from exc
