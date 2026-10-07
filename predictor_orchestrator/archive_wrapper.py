from __future__ import annotations

from copy import deepcopy
from typing import Any

from .archive_publisher import Stage3ArchivePublisher


def _fixture_id(item: dict[str, Any]) -> str:
    return str(item.get("fixture_id") or item.get("fixture_uid") or item.get("match_id_hash") or "").strip()


class EnrichedStage3ArchivePublisher:
    """Adapter that preserves the full accepted Stage 1 preference in archive input.

    Predictor policy keeps Stage 1 market/selection frozen in Stage 3. The archive
    additionally needs the real Stage 1 observed price, when one existed, for the
    mandatory matched one-unit ROI comparison. The source is the already accepted
    Stage 1 payload; nothing is inferred or synthesized here.
    """

    def __init__(self, inner: Stage3ArchivePublisher):
        self.inner = inner

    @classmethod
    def from_env_optional(cls) -> "EnrichedStage3ArchivePublisher | None":
        inner = Stage3ArchivePublisher.from_env_optional()
        return cls(inner) if inner is not None else None

    def publish(self, **kwargs: Any) -> dict[str, Any]:
        stage1_payload = kwargs.get("stage1_payload") or {}
        stage1_by_id = {
            _fixture_id(item): item
            for item in stage1_payload.get("matches") or []
            if isinstance(item, dict) and _fixture_id(item)
        }
        stage3_payload = deepcopy(kwargs.get("stage3_payload") or {})
        for row in stage3_payload.get("matches") or []:
            if not isinstance(row, dict):
                continue
            accepted_stage1 = stage1_by_id.get(_fixture_id(row)) or {}
            preference = accepted_stage1.get("preference")
            if isinstance(preference, dict):
                row["stage1_baseline"] = deepcopy(preference)
        forwarded = dict(kwargs)
        forwarded["stage3_payload"] = stage3_payload
        return self.inner.publish(**forwarded)
