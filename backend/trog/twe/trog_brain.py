import json
import re
from dataclasses import asdict, dataclass
from typing import Any


INPUT_SCHEMA_VERSION = "1.0"
OUTPUT_SCHEMA_VERSION = "1.0"
RESPONSE_KINDS = {
    "grounded_answer",
    "clarification",
    "refusal",
    "action_proposal",
    "knowledge_gap",
}
_SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:api_?key|authorization|cookie|credential|password|secret|token)(?:$|_)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|sk-[A-Za-z0-9_-]{12,})",
    re.IGNORECASE,
)


class TrogBrainValidationError(ValueError):
    pass


def reject_sensitive_data(value: Any, path: str = "request") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                raise TrogBrainValidationError(
                    f"Sensitive field is not allowed in Trog brain context: {path}.{key}"
                )
            reject_sensitive_data(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            reject_sensitive_data(nested, f"{path}[{index}]")
        return
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        raise TrogBrainValidationError(
            f"Sensitive value is not allowed in Trog brain context: {path}"
        )


def _required_text(value: Any, field_name: str, max_length: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrogBrainValidationError(f"{field_name} is required.")
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise TrogBrainValidationError(f"{field_name} is too long.")
    return cleaned


@dataclass(frozen=True)
class GroundingCitation:
    title: str
    uri: str

    @classmethod
    def from_dict(cls, value: dict) -> "GroundingCitation":
        if not isinstance(value, dict):
            raise TrogBrainValidationError("Each citation must be an object.")
        reject_sensitive_data(value, "citation")
        return cls(
            title=_required_text(value.get("title"), "citation.title", 200),
            uri=_required_text(value.get("uri"), "citation.uri", 1000),
        )


@dataclass(frozen=True)
class TrogBrainRequest:
    user_id: str
    guild_id: str
    channel_id: str
    request_text: str
    correlation_id: str
    effective_capabilities: tuple[str, ...] = ()
    community_id: str | None = None
    community_name: str | None = None
    world_id: str | None = None
    world_name: str | None = None
    grounding_facts: tuple[str, ...] = ()
    citations: tuple[GroundingCitation, ...] = ()
    schema_version: str = INPUT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: dict) -> "TrogBrainRequest":
        if not isinstance(value, dict):
            raise TrogBrainValidationError("Trog brain input must be an object.")
        reject_sensitive_data(value)
        if value.get("schema_version", INPUT_SCHEMA_VERSION) != INPUT_SCHEMA_VERSION:
            raise TrogBrainValidationError("Unsupported Trog brain input schema version.")

        capabilities = value.get("effective_capabilities") or []
        facts = value.get("grounding_facts") or []
        citations = value.get("citations") or []
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item.strip() for item in capabilities
        ):
            raise TrogBrainValidationError("effective_capabilities must be a list of names.")
        if not isinstance(facts, list) or not all(
            isinstance(item, str) and item.strip() for item in facts
        ):
            raise TrogBrainValidationError("grounding_facts must be a list of text facts.")
        if len(facts) > 20 or any(len(item) > 2000 for item in facts):
            raise TrogBrainValidationError("Grounding context exceeds the allowed size.")

        request = cls(
            schema_version=INPUT_SCHEMA_VERSION,
            user_id=_required_text(value.get("user_id"), "user_id", 100),
            guild_id=_required_text(value.get("guild_id"), "guild_id", 100),
            channel_id=_required_text(value.get("channel_id"), "channel_id", 100),
            community_id=_optional_text(value.get("community_id"), "community_id", 100),
            community_name=_optional_text(
                value.get("community_name"), "community_name", 200
            ),
            world_id=_optional_text(value.get("world_id"), "world_id", 100),
            world_name=_optional_text(value.get("world_name"), "world_name", 200),
            effective_capabilities=tuple(sorted(set(capabilities))),
            request_text=_required_text(
                value.get("request_text"), "request_text", 4000
            ),
            correlation_id=_required_text(
                value.get("correlation_id"), "correlation_id", 200
            ),
            grounding_facts=tuple(item.strip() for item in facts),
            citations=tuple(GroundingCitation.from_dict(item) for item in citations),
        )
        reject_sensitive_data(asdict(request))
        return request

    @property
    def has_unambiguous_scope(self) -> bool:
        return bool(
            self.community_id
            and self.community_name
            and self.world_id
            and self.world_name
        )

    def to_model_payload(self) -> dict:
        payload = asdict(self)
        reject_sensitive_data(payload)
        return payload


def _optional_text(
    value: Any, field_name: str, max_length: int
) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name, max_length)


@dataclass(frozen=True)
class TrogActionArgument:
    name: str
    value: str

    @classmethod
    def from_dict(cls, value: dict) -> "TrogActionArgument":
        if not isinstance(value, dict):
            raise TrogBrainValidationError(
                "Each action argument must be an object."
            )
        reject_sensitive_data(value, "action.argument")
        return cls(
            name=_required_text(value.get("name"), "action.argument.name", 100),
            value=_required_text(value.get("value"), "action.argument.value", 1000),
        )


@dataclass(frozen=True)
class TrogActionProposal:
    action_type: str
    capability: str
    world_id: str
    arguments: tuple[TrogActionArgument, ...]
    confirmation_required: bool = True

    @classmethod
    def from_dict(cls, value: dict) -> "TrogActionProposal":
        if not isinstance(value, dict):
            raise TrogBrainValidationError("action must be an object.")
        reject_sensitive_data(value, "action")
        arguments = value.get("arguments")
        if not isinstance(arguments, list):
            raise TrogBrainValidationError("action.arguments must be a list.")
        if len(arguments) > 20:
            raise TrogBrainValidationError("Too many action arguments were proposed.")
        if value.get("confirmation_required") is not True:
            raise TrogBrainValidationError(
                "Every model-proposed action must require confirmation."
            )
        return cls(
            action_type=_required_text(
                value.get("action_type"), "action.action_type", 100
            ),
            capability=_required_text(
                value.get("capability"), "action.capability", 200
            ),
            world_id=_required_text(value.get("world_id"), "action.world_id", 100),
            arguments=tuple(TrogActionArgument.from_dict(item) for item in arguments),
            confirmation_required=True,
        )


@dataclass(frozen=True)
class TrogBrainResponse:
    kind: str
    message: str
    action: TrogActionProposal | None = None
    citations: tuple[GroundingCitation, ...] = ()
    schema_version: str = OUTPUT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: dict) -> "TrogBrainResponse":
        if not isinstance(value, dict):
            raise TrogBrainValidationError("Trog brain output must be an object.")
        reject_sensitive_data(value, "response")
        if value.get("schema_version") != OUTPUT_SCHEMA_VERSION:
            raise TrogBrainValidationError("Unsupported Trog brain output schema version.")
        kind = value.get("kind")
        if kind not in RESPONSE_KINDS:
            raise TrogBrainValidationError("Unsupported Trog brain response kind.")
        action_value = value.get("action")
        action = (
            TrogActionProposal.from_dict(action_value)
            if action_value is not None
            else None
        )
        if kind == "action_proposal" and action is None:
            raise TrogBrainValidationError("An action proposal requires a typed action.")
        if kind != "action_proposal" and action is not None:
            raise TrogBrainValidationError(
                "Only an action proposal may include an action."
            )
        citations = value.get("citations") or []
        if not isinstance(citations, list):
            raise TrogBrainValidationError("citations must be a list.")
        return cls(
            schema_version=OUTPUT_SCHEMA_VERSION,
            kind=kind,
            message=_required_text(value.get("message"), "message", 4000),
            action=action,
            citations=tuple(GroundingCitation.from_dict(item) for item in citations),
        )

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self)))


def clarification_for_ambiguous_scope() -> TrogBrainResponse:
    return TrogBrainResponse(
        kind="clarification",
        message=(
            "I need to know which Community and World this request belongs to "
            "before I can answer or propose an action."
        ),
    )


def language_service_fallback() -> TrogBrainResponse:
    return TrogBrainResponse(
        kind="refusal",
        message=(
            "My language service is unavailable right now. Existing Trog server "
            "commands are still available; please try again shortly."
        ),
    )
