from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import predictor_agent_bridge as bridge


WORKFLOW_ID = "pred_20261010T120000_abcdef1234"


class PredictorAgentBridgeTests(unittest.TestCase):
    def test_reads_secret_from_server_side_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictor.env"
            path.write_text("OTHER=x\nPREDICTOR_ORCHESTRATOR_SECRET=server-only-secret\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(bridge._read_secret(path), "server-only-secret")

    def test_rejects_non_loopback_target(self):
        with patch.dict(os.environ, {"PREDICTOR_BRIDGE_ORCHESTRATOR_URL": "https://example.com"}, clear=False):
            with self.assertRaisesRegex(bridge.BridgeError, "loopback"):
                bridge._base_url()

    def test_stage2_requires_explicit_user_authorization_before_network_call(self):
        with patch.object(bridge, "_request_json") as request_json:
            with self.assertRaisesRegex(bridge.BridgeError, "user_authorized=true"):
                bridge.dispatch(
                    {
                        "action": "submit_stage",
                        "workflow_id": WORKFLOW_ID,
                        "stage": "STAGE2",
                        "generated": {},
                    },
                    secret="secret",
                )
        request_json.assert_not_called()

    def test_submit_requires_production_store_readback_and_returns_persisted_receipt(self):
        submitted = {
            "ok": True,
            "workflow_id": WORKFLOW_ID,
            "stage": "STAGE1",
            "stage_run_id": f"{WORKFLOW_ID}:stage1:1234567890",
            "policy_version": 7,
            "validated": True,
        }
        readback = {
            "ok": True,
            "workflow": {"workflow_id": WORKFLOW_ID},
            "stages": {
                "STAGE1": {
                    "stage_run_id": submitted["stage_run_id"],
                    "accepted_at": "2026-10-10T12:00:01+00:00",
                    "policy_version": 7,
                }
            },
        }
        with patch.object(bridge, "_request_json", side_effect=[submitted, readback]) as request_json:
            result = bridge.dispatch(
                {
                    "action": "submit_stage",
                    "workflow_id": WORKFLOW_ID,
                    "stage": "STAGE1",
                    "generated": {"screening_results": [], "matches": []},
                    "agent_model": "test-agent",
                },
                secret="secret",
            )
        self.assertEqual(result["bridge_receipt"]["status"], "ACCEPTED_PERSISTED")
        self.assertEqual(result["bridge_receipt"]["verification"], "PRODUCTION_STORE_READBACK")
        self.assertEqual(result["bridge_receipt"]["stage_run_id"], submitted["stage_run_id"])
        self.assertEqual(request_json.call_count, 2)
        self.assertIn("/stage1/submit", request_json.call_args_list[0].args[1])
        self.assertEqual(request_json.call_args_list[1].args[0], "GET")

    def test_submit_fails_closed_when_readback_does_not_match(self):
        submitted = {
            "ok": True,
            "stage_run_id": f"{WORKFLOW_ID}:stage1:1234567890",
        }
        readback = {
            "ok": True,
            "stages": {
                "STAGE1": {
                    "stage_run_id": f"{WORKFLOW_ID}:stage1:different00",
                    "accepted_at": "2026-10-10T12:00:01+00:00",
                }
            },
        }
        with patch.object(bridge, "_request_json", side_effect=[submitted, readback]):
            with self.assertRaisesRegex(bridge.BridgeError, "readback"):
                bridge.dispatch(
                    {
                        "action": "submit_stage",
                        "workflow_id": WORKFLOW_ID,
                        "stage": "STAGE1",
                        "generated": {},
                    },
                    secret="secret",
                )

    def test_only_whitelisted_actions_are_allowed(self):
        with self.assertRaisesRegex(bridge.BridgeError, "unsupported bridge action"):
            bridge.dispatch({"action": "shell", "workflow_id": WORKFLOW_ID}, secret="secret")

    def test_invalid_workflow_id_is_rejected_before_network_call(self):
        with patch.object(bridge, "_request_json") as request_json:
            with self.assertRaisesRegex(bridge.BridgeError, "invalid workflow_id"):
                bridge.dispatch({"action": "get_workflow", "workflow_id": "../../etc/passwd"}, secret="secret")
        request_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
