from __future__ import annotations

from typing import Any

from .archive_publisher import Stage3ArchivePublisher
from .formal_publication import FormalPublicationError, formal_result_from_store
from .lifecycle_store import PredictorLifecycleStore
from .service import OrchestratorError, PredictorOrchestrator


_UNSET = object()


class StrictPredictorOrchestrator(PredictorOrchestrator):
    """Production Predictor boundary.

    The base orchestrator already validates and atomically accepts stages. This
    subclass makes publication depend on reading that accepted row back from the
    durable store, and it attaches the Stage 3 Learning Archive/Diary lifecycle.
    """

    def __init__(
        self,
        *,
        config,
        store,
        llm,
        archive_publisher: Any = _UNSET,
        lifecycle_store: PredictorLifecycleStore | None = None,
    ):
        super().__init__(config=config, store=store, llm=llm)
        self.archive_publisher = (
            Stage3ArchivePublisher.from_env_optional()
            if archive_publisher is _UNSET
            else archive_publisher
        )
        self.lifecycle_store = lifecycle_store or PredictorLifecycleStore(config.state_db_path)

    @staticmethod
    def _formal_rows(stage3_payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            item
            for item in stage3_payload.get("matches") or []
            if isinstance(item, dict)
            and str(item.get("decision") or "").upper() in {"BET", "WATCH"}
        ]

    def _pending_archive(
        self,
        *,
        workflow_id: str,
        stage_run_id: str,
        rows: list[dict[str, Any]],
        error: str,
    ) -> dict[str, Any]:
        for row in rows:
            fixture_id = str(row.get("fixture_id") or "").strip()
            if not fixture_id:
                continue
            self.lifecycle_store.upsert(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                fixture_id=fixture_id,
                case_id=None,
                archive_status="ARCHIVE_PENDING",
                diary_status="DIARY_PENDING",
                error=error[:500],
            )
        return self.lifecycle_store.summary(workflow_id, stage_run_id)

    def _archive_stage3(
        self,
        *,
        workflow_id: str,
        stage_run_id: str,
        stage3_payload: dict[str, Any],
    ) -> dict[str, Any]:
        formal_rows = self._formal_rows(stage3_payload)
        if not formal_rows:
            return {
                "status": "NOT_APPLICABLE",
                "formal_cases": 0,
                "cases": [],
                "diary_status": "NOT_REQUIRED",
            }
        if self.archive_publisher is None:
            return self._pending_archive(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                rows=formal_rows,
                error="Learning Archive publisher is not configured",
            )

        workflow = self.get_workflow(workflow_id)
        stage1_record = self.store.get_stage_output(workflow_id, "STAGE1")
        stage2_record = self.store.get_stage_output(workflow_id, "STAGE2")
        trusted = self.store.get_trusted_context(workflow_id, "STAGE1")
        if stage1_record is None or stage2_record is None or trusted is None:
            return self._pending_archive(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                rows=formal_rows,
                error="Accepted predecessor/context state is unavailable for archive publication",
            )

        try:
            published = self.archive_publisher.publish(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                workflow_scope=workflow.scope,
                stage1_payload=stage1_record["payload"],
                stage2_payload=stage2_record["payload"],
                stage3_payload=stage3_payload,
                stage1_context=trusted["context"],
            )
        except Exception as exc:
            return self._pending_archive(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                rows=formal_rows,
                error=f"Archive publication failed: {exc}",
            )

        returned: dict[str, dict[str, Any]] = {}
        for item in published.get("cases") or []:
            if isinstance(item, dict) and str(item.get("fixture_id") or "").strip():
                returned[str(item["fixture_id"]).strip()] = item

        diary_status = str(published.get("diary_status") or "DIARY_PENDING")
        diary = published.get("diary") if isinstance(published.get("diary"), dict) else {}
        diary_reference = diary.get("reference")
        for row in formal_rows:
            fixture_id = str(row.get("fixture_id") or "").strip()
            if not fixture_id:
                continue
            item = returned.get(fixture_id)
            if item is None:
                self.lifecycle_store.upsert(
                    workflow_id=workflow_id,
                    stage_run_id=stage_run_id,
                    fixture_id=fixture_id,
                    case_id=None,
                    archive_status="ARCHIVE_PENDING",
                    diary_status=diary_status,
                    diary_reference=diary_reference,
                    error="Archive publisher returned no receipt for formal Stage 3 row",
                )
                continue
            self.lifecycle_store.upsert(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                fixture_id=fixture_id,
                case_id=item.get("case_id"),
                archive_status=str(item.get("archive_status") or "ARCHIVE_PENDING"),
                archive_reference=item.get("archive_reference"),
                archive_commit=item.get("archive_commit"),
                checksum_summary=item.get("checksum_summary"),
                diary_status=str(item.get("diary_status") or diary_status),
                diary_reference=item.get("diary_reference") or diary_reference,
                error=item.get("error"),
            )

        summary = self.lifecycle_store.summary(workflow_id, stage_run_id)
        summary["diary"] = diary
        return summary

    def _strict_result(self, result: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str(result.get("workflow_id") or "").strip()
        stage = str(result.get("stage") or "").upper()
        stage_run_id = str(result.get("stage_run_id") or "").strip()
        if not workflow_id or not stage or not stage_run_id:
            raise OrchestratorError("accepted Predictor result is missing publication identity")
        try:
            report, receipt = formal_result_from_store(
                store=self.store,
                workflow_id=workflow_id,
                stage=stage,
                expected_stage_run_id=stage_run_id,
            )
        except FormalPublicationError as exc:
            raise OrchestratorError(f"formal publication gate failed: {exc}") from exc

        strict = dict(result)
        strict["report"] = report
        strict["formal_publication"] = True
        strict["publication_receipt"] = receipt
        if stage == "STAGE3":
            accepted = self.store.get_stage_output(workflow_id, "STAGE3")
            if accepted is None:
                raise OrchestratorError("accepted Stage 3 disappeared before archive lifecycle")
            strict["archive"] = self._archive_stage3(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                stage3_payload=accepted["payload"],
            )
        else:
            strict["archive"] = {
                "status": "NOT_APPLICABLE",
                "formal_cases": 0,
                "cases": [],
                "diary_status": "NOT_REQUIRED",
            }
        return strict

    def submit_generated_stage(self, **kwargs: Any) -> dict[str, Any]:
        return self._strict_result(super().submit_generated_stage(**kwargs))

    def run_stage(self, **kwargs: Any) -> dict[str, Any]:
        return self._strict_result(super().run_stage(**kwargs))
