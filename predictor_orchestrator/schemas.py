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

STAGE2_FACT_SCHEMA = _object(
    {
        "kind": {"type": "string", "enum": ["FACT", "INFERENCE"]},
        "relationship": {"type": "string", "enum": ["SUPPORTS", "CONTRADICTS", "NEUTRAL"]},
        "claim": {"type": "string", "minLength": 1},
        "source": _STRING_OR_NULL,
        "source_tier": {"type": ["string", "null"], "enum": ["A", "B", "C", "D", None]},
        "observed_at": _STRING_OR_NULL,
    },
    ["kind", "relationship", "claim", "source", "source_tier", "observed_at"],
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
                            "squad_checked": {"type": "boolean"},
                            "performance_checked": {"type": "boolean"},
                            "counter_checked": {"type": "boolean"},
                            "coverage_classified": {"type": "boolean"},
                        },
                        ["squad_checked", "performance_checked", "counter_checked", "coverage_classified"],
                    ),
                    "facts": {
                        "type": "array",
                        "maxItems": 6,
                        "items": deepcopy(STAGE2_FACT_SCHEMA),
                    },
                    "research_support": {"type": "string", "minLength": 1},
                    "research_counter": {"type": "string", "minLength": 1},
                    "important_absence": _STRING_OR_NULL,
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
                    "research_support",
                    "research_counter",
                    "important_absence",
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
