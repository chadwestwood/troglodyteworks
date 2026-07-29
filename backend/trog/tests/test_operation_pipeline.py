import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.operation_pipeline import OperationPipeline, OperationRequest, OperationSpec


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


class OperationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = OperationPipeline(
            (
                OperationSpec("status", "instance.status.read"),
                OperationSpec(
                    "add_mod",
                    "instance.mods.write",
                    requires_confirmation=True,
                    required_argument="mod_reference",
                ),
                OperationSpec(
                    "restart",
                    "instance.restart.execute",
                    requires_confirmation=True,
                ),
            )
        )
        self.executions = []

    def run_request(self, request, decision=Decision(True, "authorized")):
        return self.pipeline.run(
            request,
            authorize=lambda _capability: decision,
            execute=lambda operation, spec, authorization: self.executions.append(
                (operation, spec, authorization)
            )
            or "tool result",
        )

    def test_unknown_intent_fails_before_authorization_or_execution(self):
        result = self.run_request(OperationRequest("delete_everything"))

        self.assertEqual(result.stage, "intent")
        self.assertEqual(result.code, "unsupported_intent")
        self.assertEqual(self.executions, [])

    def test_permission_denial_stops_before_validation_confirmation_and_tool(self):
        result = self.run_request(
            OperationRequest("add_mod"),
            Decision(False, "capability_not_granted"),
        )

        self.assertEqual(result.stage, "permission")
        self.assertEqual(result.code, "capability_not_granted")
        self.assertEqual(self.executions, [])

    def test_argument_validation_stops_before_confirmation_and_tool(self):
        result = self.run_request(OperationRequest("add_mod"))

        self.assertEqual(result.stage, "validation")
        self.assertEqual(result.code, "mod_reference_required")
        self.assertEqual(self.executions, [])

    def test_confirmation_stops_before_tool(self):
        result = self.run_request(OperationRequest("restart"))

        self.assertEqual(result.stage, "confirmation")
        self.assertEqual(result.code, "confirmation_required")
        self.assertEqual(self.executions, [])

    def test_confirmed_request_executes_exactly_once(self):
        result = self.run_request(
            OperationRequest("add_mod", argument="Silent Structures", confirmed=True)
        )

        self.assertTrue(result.executed)
        self.assertEqual(result.value, "tool result")
        self.assertEqual(len(self.executions), 1)
        self.assertEqual(self.executions[0][0].argument, "Silent Structures")

    def test_read_request_does_not_require_confirmation(self):
        result = self.run_request(OperationRequest("status"))

        self.assertTrue(result.executed)
        self.assertEqual(len(self.executions), 1)


if __name__ == "__main__":
    unittest.main()
