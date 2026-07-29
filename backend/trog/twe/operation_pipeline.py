"""Deterministic operation pipeline shared by conversational entry points.

Language interpretation may produce an intent and arguments, but this module
owns every safety-sensitive transition after that point.  In particular, a
tool is never called before permission, argument validation, and required
confirmation have all succeeded.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class OperationSpec:
    intent: str
    capability: str
    requires_confirmation: bool = False
    required_argument: str | None = None


@dataclass(frozen=True)
class OperationRequest:
    intent: str
    argument: str | None = None
    confirmed: bool = False


@dataclass(frozen=True)
class PipelineResult:
    stage: str
    code: str
    request: OperationRequest
    spec: OperationSpec | None = None
    authorization: Any = None
    value: Any = None

    @property
    def executed(self) -> bool:
        return self.stage == "tool"


class OperationPipeline:
    def __init__(self, specs: tuple[OperationSpec, ...] | list[OperationSpec]):
        self._specs = {spec.intent: spec for spec in specs}

    def run(
        self,
        request: OperationRequest,
        *,
        authorize: Callable[[str], Any],
        execute: Callable[[OperationRequest, OperationSpec, Any], Any],
    ) -> PipelineResult:
        spec = self._specs.get(request.intent)
        if spec is None:
            return PipelineResult("intent", "unsupported_intent", request)

        decision = authorize(spec.capability)
        if not bool(getattr(decision, "allowed", False)):
            return PipelineResult(
                "permission",
                str(getattr(decision, "reason", "permission_denied")),
                request,
                spec,
                authorization=decision,
            )

        argument = (request.argument or "").strip()
        if spec.required_argument and not argument:
            return PipelineResult(
                "validation",
                f"{spec.required_argument}_required",
                request,
                spec,
                authorization=decision,
            )

        if spec.requires_confirmation and request.confirmed is not True:
            return PipelineResult(
                "confirmation",
                "confirmation_required",
                request,
                spec,
                authorization=decision,
            )

        value = execute(request, spec, decision)
        return PipelineResult(
            "tool",
            "executed",
            request,
            spec,
            authorization=decision,
            value=value,
        )

