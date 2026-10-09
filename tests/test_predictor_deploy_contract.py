from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PredictorDeployContractTests(unittest.TestCase):
    def test_wsgi_uses_strict_orchestrator(self):
        text = (ROOT / "predictor_orchestrator" / "wsgi.py").read_text(encoding="utf-8")
        self.assertIn("StrictPredictorOrchestrator", text)
        self.assertIn("orchestrator=orchestrator", text)

    def test_systemd_requires_archive_write_probe_and_key(self):
        text = (ROOT / "deploy" / "systemd" / "smartxflow-predictor-orchestrator.service").read_text(encoding="utf-8")
        self.assertIn("LEARNING_ARCHIVE_GIT_SSH_KEY=/var/lib/smartxflow-prematch/github_learning_archive_ed25519", text)
        self.assertIn("verify_learning_archive_ssh_write.py", text)
        self.assertIn("predictor_orchestrator.wsgi:app", text)

    def test_postmatch_timer_uses_diary_aware_finalizer(self):
        text = (ROOT / "deploy" / "systemd" / "smartxflow-learning-archive-postmatch.service").read_text(encoding="utf-8")
        self.assertIn("settle_due_learning_cases_with_diary.py", text)
        self.assertNotIn("ExecStart=/opt/smartxflow/venv/bin/python /opt/smartxflow/scripts/settle_due_learning_cases_fast.py", text)

    def test_predictor_deploy_verifies_exact_sha_health_and_archive_retry(self):
        text = (ROOT / ".github" / "workflows" / "deploy-predictor-orchestrator.yml").read_text(encoding="utf-8")
        self.assertIn("github.event.workflow_run.head_sha", text)
        self.assertIn("production HEAD $HEAD != approved deploy SHA $DEPLOY_SHA", text)
        self.assertIn("for _ in $(seq 1 90)", text)
        self.assertIn("journalctl -u smartxflow-predictor-orchestrator.service", text)
        self.assertIn("HEALTH=\"\"", text)
        self.assertIn("curl -fsS --max-time 2 http://127.0.0.1:8011/healthz", text)
        self.assertIn("service never became HTTP-ready", text)
        self.assertIn("stage1_source_enabled", text)
        self.assertIn("retry_predictor_archive_pending.py", text)
        self.assertIn("PREDICTOR_ARCHIVE_RETRY_OK", text)
        self.assertIn("PREDICTOR_DEPLOY_OK", text)

    def test_archive_retry_script_is_fail_closed_and_uses_durable_stage3(self):
        text = (ROOT / "scripts" / "retry_predictor_archive_pending.py").read_text(encoding="utf-8")
        self.assertIn("predictor_archive_lifecycle", text)
        self.assertIn("store.get_stage_output(workflow_id, \"STAGE3\")", text)
        self.assertIn("Learning Archive publisher is not configured", text)
        self.assertIn("remaining_pending", text)
        self.assertIn("--dotenv", text)


if __name__ == "__main__":
    unittest.main()
