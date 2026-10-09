from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PredictorDeployContractTests(unittest.TestCase):
    def test_wsgi_uses_strict_orchestrator(self):
        text = (ROOT / "predictor_orchestrator" / "wsgi.py").read_text(encoding="utf-8")
        self.assertIn("StrictPredictorOrchestrator", text)
        self.assertIn("orchestrator=orchestrator", text)

    def test_systemd_requires_archive_write_probe_key_and_durable_secret_env(self):
        text = (ROOT / "deploy" / "systemd" / "smartxflow-predictor-orchestrator.service").read_text(encoding="utf-8")
        self.assertIn("LEARNING_ARCHIVE_GIT_SSH_KEY=/var/lib/smartxflow-prematch/github_learning_archive_ed25519", text)
        self.assertIn("EnvironmentFile=-/var/lib/smartxflow-predictor/predictor-orchestrator.env", text)
        self.assertIn("verify_learning_archive_ssh_write.py", text)
        self.assertIn("predictor_orchestrator.wsgi:app", text)

    def test_postmatch_timer_uses_diary_aware_finalizer(self):
        text = (ROOT / "deploy" / "systemd" / "smartxflow-learning-archive-postmatch.service").read_text(encoding="utf-8")
        self.assertIn("settle_due_learning_cases_with_diary.py", text)
        self.assertNotIn("ExecStart=/opt/smartxflow/venv/bin/python /opt/smartxflow/scripts/settle_due_learning_cases_fast.py", text)

    def test_predictor_deploy_verifies_exact_sha_health_secret_and_archive_retry(self):
        text = (ROOT / ".github" / "workflows" / "deploy-predictor-orchestrator.yml").read_text(encoding="utf-8")
        self.assertIn("github.event.workflow_run.head_sha", text)
        self.assertIn("production HEAD $HEAD != approved deploy SHA $DEPLOY_SHA", text)
        self.assertIn("predictor-orchestrator.env", text)
        self.assertIn("openssl rand -hex 32", text)
        self.assertIn("chmod 0640", text)
        self.assertIn("PREDICTOR_ORCHESTRATOR_SECRET", text)
        self.assertIn("for _ in $(seq 1 90)", text)
        self.assertIn("journalctl -u smartxflow-predictor-orchestrator.service", text)
        self.assertIn("HEALTH=\"\"", text)
        self.assertIn("curl -fsS --max-time 2 http://127.0.0.1:8011/healthz", text)
        self.assertIn("service never became HTTP-ready", text)
        self.assertIn("stage1_source_enabled", text)
        self.assertIn("PYTHONPATH=/opt/smartxflow", text)
        self.assertIn("retry_predictor_archive_pending.py", text)
        self.assertIn("--db /var/lib/smartxflow-predictor/predictor-orchestrator.sqlite3", text)
        self.assertIn("--scan-root /opt/smartxflow/data", text)
        self.assertIn("--scan-root /var/lib/smartxflow-predictor", text)
        self.assertIn("scanned_databases", text)
        self.assertIn("PREDICTOR_ARCHIVE_RETRY_OK", text)
        self.assertIn("PREDICTOR_DEPLOY_OK", text)
        self.assertLess(
            text.index("openssl rand -hex 32"),
            text.index("systemctl restart smartxflow-predictor-orchestrator.service"),
        )
        self.assertLess(
            text.index("predictor-orchestrator.env"),
            text.index("systemctl restart smartxflow-predictor-orchestrator.service"),
        )

    def test_predictor_deploy_recovers_exact_stranded_9_october_workflow(self):
        text = (ROOT / ".github" / "workflows" / "deploy-predictor-orchestrator.yml").read_text(encoding="utf-8")
        self.assertIn("pred_20261009T134410_bef4b19b53", text)
        self.assertIn("pred_20261009T134410_bef4b19b53:stage3:a31d6ecd09", text)
        self.assertIn("--workflow-id \"$TARGET_WORKFLOW\"", text)
        self.assertIn("--require-workflow", text)
        self.assertIn("PREDICTOR_LEGACY_RECOVERY_OK", text)
        self.assertIn("learning_archive_data/diaries/2026/10/09/predictions.md", text)
        self.assertIn("case_count != 14", text)
        self.assertIn("PREDICTOR_LEGACY_DIARY_OK", text)

    def test_archive_retry_script_is_fail_closed_uses_durable_stage3_and_targets_legacy_dbs(self):
        text = (ROOT / "scripts" / "retry_predictor_archive_pending.py").read_text(encoding="utf-8")
        self.assertIn("predictor_archive_lifecycle", text)
        self.assertIn("store.get_stage_output(workflow_id, \"STAGE3\")", text)
        self.assertIn("Learning Archive publisher is not configured", text)
        self.assertIn("remaining_pending", text)
        self.assertIn("--dotenv", text)
        self.assertIn("--scan-root", text)
        self.assertIn("--workflow-id", text)
        self.assertIn("--require-workflow", text)
        self.assertIn("TARGET_NOT_FOUND", text)
        self.assertIn("_candidate_db_paths", text)
        self.assertIn("archive_commits", text)
        self.assertIn("diary_references", text)
        self.assertIn("matched_workflows", text)


if __name__ == "__main__":
    unittest.main()
