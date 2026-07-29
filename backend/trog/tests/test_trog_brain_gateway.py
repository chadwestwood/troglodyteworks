import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.services.trog_brain_gateway import OpenAIResponsesGateway
from twe.trog_brain import (
    TrogBrainRequest,
    TrogBrainResponse,
    TrogBrainValidationError,
)


def request_payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "user_id": "user-1",
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "community_id": "community-1",
        "community_name": "Cohorts in the Wild",
        "world_id": "world-1",
        "world_name": "Genesis",
        "effective_capabilities": ["instance.status.read"],
        "request_text": "Is the server ready?",
        "correlation_id": "correlation-1",
        "grounding_facts": ["Provider status: ready"],
        "citations": [
            {
                "title": "World status",
                "uri": "https://example.test/status",
            }
        ],
    }
    payload.update(overrides)
    return payload


def response_payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "kind": "grounded_answer",
        "message": "Genesis is ready.",
        "action": None,
        "citations": [],
    }
    payload.update(overrides)
    return payload


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


class TrogBrainContractTests(unittest.TestCase):
    def test_input_is_versioned_and_requires_actor_and_discord_context(self):
        request = TrogBrainRequest.from_dict(request_payload())
        self.assertEqual(request.schema_version, "1.0")
        self.assertEqual(request.guild_id, "guild-1")
        self.assertEqual(request.effective_capabilities, ("instance.status.read",))

        with self.assertRaises(TrogBrainValidationError):
            TrogBrainRequest.from_dict(request_payload(channel_id=""))

    def test_sensitive_fields_and_values_are_rejected(self):
        with self.assertRaises(TrogBrainValidationError):
            TrogBrainRequest.from_dict(
                request_payload(provider_api_token="should-never-cross-boundary")
            )
        with self.assertRaises(TrogBrainValidationError):
            TrogBrainRequest.from_dict(
                request_payload(grounding_facts=["Authorization: Bearer abcdefghijklmnop"])
            )

    def test_ambiguous_scope_fails_closed_without_calling_model(self):
        client = FakeClient(SimpleNamespace(output=[], output_text=""))
        gateway = OpenAIResponsesGateway(
            Config(
                database_url="postgresql://unused",
                openai_api_key="not-a-real-key",
                trog_brain_enabled=True,
            ),
            client=client,
        )
        request = TrogBrainRequest.from_dict(request_payload(world_id=None))

        response = gateway.respond(request)

        self.assertEqual(response.kind, "clarification")
        self.assertEqual(client.responses.calls, [])

    def test_typed_action_always_requires_confirmation(self):
        valid = TrogBrainResponse.from_dict(
            response_payload(
                kind="action_proposal",
                message="I can propose restarting Genesis.",
                action={
                    "action_type": "restart_world",
                    "capability": "instance.restart.execute",
                    "world_id": "world-1",
                    "arguments": [],
                    "confirmation_required": True,
                },
            )
        )
        self.assertTrue(valid.action.confirmation_required)

        with self.assertRaises(TrogBrainValidationError):
            TrogBrainResponse.from_dict(
                response_payload(
                    kind="action_proposal",
                    action={
                        "action_type": "restart_world",
                        "capability": "instance.restart.execute",
                        "world_id": "world-1",
                        "arguments": [],
                        "confirmation_required": False,
                    },
                )
            )

    def test_gateway_uses_configured_model_limit_and_structured_output(self):
        model_response = SimpleNamespace(
            output=[SimpleNamespace(type="message")],
            output_text=json.dumps(response_payload()),
        )
        client = FakeClient(model_response)
        config = Config(
            database_url="postgresql://unused",
            openai_api_key="not-a-real-key",
            trog_brain_enabled=True,
            trog_brain_model="configured-model",
            trog_brain_max_output_tokens=321,
        )
        gateway = OpenAIResponsesGateway(config, client=client)

        response = gateway.respond(TrogBrainRequest.from_dict(request_payload()))

        self.assertEqual(response.kind, "grounded_answer")
        call = client.responses.calls[0]
        self.assertEqual(call["model"], "configured-model")
        self.assertEqual(call["max_output_tokens"], 321)
        self.assertEqual(call["text"]["format"]["type"], "json_schema")
        sent_context = json.loads(call["input"])
        self.assertNotIn("openai_api_key", sent_context)
        self.assertEqual(sent_context["world_id"], "world-1")

    def test_missing_key_returns_deterministic_fallback(self):
        client = FakeClient(SimpleNamespace(output=[], output_text=""))
        gateway = OpenAIResponsesGateway(
            Config(database_url="postgresql://unused", trog_brain_enabled=True),
            client=client,
        )
        response = gateway.respond(TrogBrainRequest.from_dict(request_payload()))
        self.assertEqual(response.kind, "refusal")
        self.assertEqual(client.responses.calls, [])

    def test_model_cannot_expand_capabilities_or_change_world(self):
        for capability, world_id in (
            ("instance.restart.execute", "world-1"),
            ("instance.status.read", "another-world"),
        ):
            model_response = SimpleNamespace(
                output=[SimpleNamespace(type="message")],
                output_text=json.dumps(
                    response_payload(
                        kind="action_proposal",
                        message="I can propose that action.",
                        action={
                            "action_type": "restart_world",
                            "capability": capability,
                            "world_id": world_id,
                            "arguments": [],
                            "confirmation_required": True,
                        },
                    )
                ),
            )
            gateway = OpenAIResponsesGateway(
                Config(
                    database_url="postgresql://unused",
                    openai_api_key="not-a-real-key",
                    trog_brain_enabled=True,
                ),
                client=FakeClient(model_response),
            )
            response = gateway.respond(TrogBrainRequest.from_dict(request_payload()))
            self.assertEqual(response.kind, "refusal")

    def test_malformed_output_and_tool_calls_return_fallback(self):
        for model_response in (
            SimpleNamespace(output=[SimpleNamespace(type="message")], output_text="{"),
            SimpleNamespace(
                output=[SimpleNamespace(type="function_call")],
                output_text=json.dumps(response_payload()),
            ),
        ):
            gateway = OpenAIResponsesGateway(
                Config(
                    database_url="postgresql://unused",
                    openai_api_key="not-a-real-key",
                    trog_brain_enabled=True,
                ),
                client=FakeClient(model_response),
            )
            response = gateway.respond(TrogBrainRequest.from_dict(request_payload()))
            self.assertEqual(response.kind, "refusal")


if __name__ == "__main__":
    unittest.main()
