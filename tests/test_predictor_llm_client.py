from __future__ import annotations

import unittest

from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.llm_client import LLMClientError, OpenAIResponsesClient


class FakeResponse:
    def __init__(self, *, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


class PredictorLLMClientTests(unittest.TestCase):
    @staticmethod
    def config(*, web_search=True):
        return OrchestratorConfig(
            api_key="test-key",
            api_base="https://api.openai.com/v1",
            model="gpt-6.1-sol",
            state_db_path=":memory:",
            service_secret="test-secret",
            max_attempts=3,
            request_timeout_seconds=45,
            stage2_web_search=web_search,
            max_output_tokens=4000,
        )

    @staticmethod
    def successful_response():
        return FakeResponse(
            body={
                "id": "resp_test",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"matches":[]}',
                            }
                        ],
                    }
                ],
            }
        )

    def test_stage1_uses_strict_responses_schema_without_web_search(self):
        client = OpenAIResponsesClient(self.config())
        fake = FakeSession(self.successful_response())
        client._session = fake
        schema = {"type": "object", "properties": {"matches": {"type": "array"}}, "required": ["matches"], "additionalProperties": False}
        payload, response_id = client.generate(
            stage="STAGE1",
            system_prompt="system",
            user_prompt="user",
            schema=schema,
        )
        self.assertEqual(payload, {"matches": []})
        self.assertEqual(response_id, "resp_test")
        request = fake.calls[0]
        self.assertEqual(request["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(request["json"]["model"], "gpt-6.1-sol")
        self.assertFalse(request["json"]["store"])
        self.assertNotIn("tools", request["json"])
        fmt = request["json"]["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertTrue(fmt["strict"])
        self.assertEqual(fmt["schema"], schema)

    def test_stage2_adds_web_search_tool_only_when_enabled(self):
        client = OpenAIResponsesClient(self.config(web_search=True))
        fake = FakeSession(self.successful_response())
        client._session = fake
        client.generate(
            stage="STAGE2",
            system_prompt="system",
            user_prompt="user",
            schema={"type": "object"},
        )
        request_body = fake.calls[0]["json"]
        self.assertEqual(request_body["tools"], [{"type": "web_search"}])
        self.assertEqual(request_body["tool_choice"], "auto")

    def test_http_error_fails_closed(self):
        client = OpenAIResponsesClient(self.config())
        client._session = FakeSession(FakeResponse(status_code=400, headers={"x-request-id": "req_123"}))
        with self.assertRaises(LLMClientError) as caught:
            client.generate(
                stage="STAGE1",
                system_prompt="system",
                user_prompt="user",
                schema={"type": "object"},
            )
        self.assertIn("HTTP 400", str(caught.exception))
        self.assertIn("req_123", str(caught.exception))

    def test_refusal_fails_closed(self):
        client = OpenAIResponsesClient(self.config())
        client._session = FakeSession(
            FakeResponse(
                body={
                    "id": "resp_refusal",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "refusal", "refusal": "cannot comply"}],
                        }
                    ],
                }
            )
        )
        with self.assertRaises(LLMClientError):
            client.generate(
                stage="STAGE1",
                system_prompt="system",
                user_prompt="user",
                schema={"type": "object"},
            )


if __name__ == "__main__":
    unittest.main()
