import json
import logging
from typing import Protocol

from ..config import Config
from ..trog_brain import (
    OUTPUT_SCHEMA_VERSION,
    TrogBrainRequest,
    TrogBrainResponse,
    TrogBrainValidationError,
    clarification_for_ambiguous_scope,
    language_service_fallback,
)


LOGGER = logging.getLogger("twe.trog_brain")
_ALLOWED_OUTPUT_ITEM_TYPES = {"message", "reasoning"}

TROG_BRAIN_OUTPUT_FORMAT = {
    "type": "json_schema",
    "name": "trog_brain_response",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "kind",
            "message",
            "action",
            "citations",
        ],
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": [OUTPUT_SCHEMA_VERSION],
            },
            "kind": {
                "type": "string",
                "enum": [
                    "grounded_answer",
                    "clarification",
                    "refusal",
                    "action_proposal",
                ],
            },
            "message": {"type": "string"},
            "action": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "action_type",
                            "capability",
                            "world_id",
                            "arguments",
                            "confirmation_required",
                        ],
                        "properties": {
                            "action_type": {"type": "string"},
                            "capability": {"type": "string"},
                            "world_id": {"type": "string"},
                            "arguments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["name", "value"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                },
                            },
                            "confirmation_required": {
                                "type": "boolean",
                                "enum": [True],
                            },
                        },
                    },
                ]
            },
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "uri"],
                    "properties": {
                        "title": {"type": "string"},
                        "uri": {"type": "string"},
                    },
                },
            },
        },
    },
}

TROG_BRAIN_INSTRUCTIONS = """
You are Trog's reasoning layer for Troglodyte Works.
Answer only questions about the connected game World, gameplay, game-server
administration, settings, mods, players, or troubleshooting. Politely refuse
unrelated topics.
Use the supplied tenant-scoped context and grounding facts. You may use stable,
general game-administration knowledge for advice, but never present an assumed
value as the connected World's current configuration.
For grounded advisory answers, sound like Trog: a warm, practical guide helping
a player understand one manageable choice. Keep the response concise and easy
to scan in Discord:
- Prefer about 120 words or fewer unless the user asks for more detail.
- Open with a friendly plain-language sentence such as "Let's check it out."
- Use short Discord markdown sections. Prefer "What to check", "What I'd try",
  and "Why", with no more than two bullets in each section.
- If exact current values are supplied, show them under "What I see now".
  Otherwise, do not imply that you inspected or can see the current values.
- End with one clear next step or a short offer to prepare a proposed change.
- Avoid dense paragraphs, technical preambles, repeated caveats, and labels
  such as "Conservative recommendation".
Never claim to have executed an action.
Never grant or expand permissions.
Never request, reveal, infer, or handle provider credentials or secrets.
If the Community or World is unclear, ask for clarification.
If the user requests an action, return only a typed action proposal and require
confirmation. The application will independently authorize, confirm, and execute
any proposal. If the required capability is absent, refuse the action.
Do not invent provider state, server status, player names, mods, or citations.
""".strip()


class TrogBrainGateway(Protocol):
    def respond(self, request: TrogBrainRequest) -> TrogBrainResponse:
        ...


class OpenAIResponsesGateway:
    def __init__(self, config: Config, client=None):
        self.config = config
        self._client = client

    def respond(self, request: TrogBrainRequest) -> TrogBrainResponse:
        if not request.has_unambiguous_scope:
            return clarification_for_ambiguous_scope()
        if not self.config.trog_brain_enabled or not self.config.openai_api_key:
            return language_service_fallback()

        response = None
        try:
            response = self.client.responses.create(
                model=self.config.trog_brain_model,
                instructions=TROG_BRAIN_INSTRUCTIONS,
                input=json.dumps(
                    request.to_model_payload(),
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                text={"format": TROG_BRAIN_OUTPUT_FORMAT},
                max_output_tokens=self.config.trog_brain_max_output_tokens,
                reasoning={"effort": "low"},
            )
            self._require_completed_response(response)
            self._reject_unexpected_tool_calls(response)
            result = TrogBrainResponse.from_dict(json.loads(response.output_text))
            if result.action and (
                result.action.world_id != request.world_id
                or result.action.capability not in request.effective_capabilities
            ):
                LOGGER.warning(
                    "Trog brain proposed an unauthorized action correlation_id=%s",
                    request.correlation_id,
                )
                return TrogBrainResponse(
                    kind="refusal",
                    message="You do not have permission to request that action for this World.",
                )
            return result
        except (
            json.JSONDecodeError,
            TrogBrainValidationError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            diagnostics = _safe_response_diagnostics(response)
            LOGGER.warning(
                "Trog brain returned an invalid response correlation_id=%s "
                "error_type=%s response_status=%s incomplete_reason=%s "
                "output_text_length=%s output_item_types=%s",
                request.correlation_id,
                type(exc).__name__,
                diagnostics["status"],
                diagnostics["incomplete_reason"],
                diagnostics["output_text_length"],
                diagnostics["output_item_types"],
            )
            return language_service_fallback()
        except Exception as exc:
            LOGGER.warning(
                "Trog brain request failed correlation_id=%s error_type=%s "
                "status_code=%s error_code=%s",
                request.correlation_id,
                type(exc).__name__,
                getattr(exc, "status_code", None),
                _safe_error_code(exc),
            )
            return language_service_fallback()

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.config.openai_api_key,
                timeout=self.config.trog_brain_timeout_seconds,
                max_retries=self.config.trog_brain_max_retries,
            )
        return self._client

    @staticmethod
    def _require_completed_response(response) -> None:
        status = getattr(response, "status", "completed")
        if status != "completed":
            raise TrogBrainValidationError(
                "The model response did not complete."
            )
        if not getattr(response, "output_text", ""):
            raise TrogBrainValidationError(
                "The model response contained no output text."
            )

    @staticmethod
    def _reject_unexpected_tool_calls(response) -> None:
        for item in getattr(response, "output", ()) or ():
            item_type = (
                item.get("type")
                if isinstance(item, dict)
                else getattr(item, "type", None)
            )
            if item_type not in _ALLOWED_OUTPUT_ITEM_TYPES:
                raise TrogBrainValidationError(
                    "The model attempted an unapproved tool call."
                )


def build_trog_brain_gateway(config: Config, client=None) -> TrogBrainGateway:
    return OpenAIResponsesGateway(config, client=client)


def _safe_error_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    if code:
        return str(code)
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict) and error.get("code"):
        return str(error["code"])
    return None


def _safe_response_diagnostics(response) -> dict[str, object]:
    if response is None:
        return {
            "status": None,
            "incomplete_reason": None,
            "output_text_length": 0,
            "output_item_types": (),
        }

    incomplete_details = getattr(response, "incomplete_details", None)
    if isinstance(incomplete_details, dict):
        incomplete_reason = incomplete_details.get("reason")
    else:
        incomplete_reason = getattr(incomplete_details, "reason", None)

    item_types = []
    for item in getattr(response, "output", ()) or ():
        item_type = (
            item.get("type")
            if isinstance(item, dict)
            else getattr(item, "type", None)
        )
        item_types.append(str(item_type or "unknown"))

    output_text = getattr(response, "output_text", "") or ""
    return {
        "status": getattr(response, "status", None),
        "incomplete_reason": incomplete_reason,
        "output_text_length": len(output_text),
        "output_item_types": tuple(item_types),
    }
