import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.rate_limits import RateLimitRule, consume_request_limit, rule_for_request


class RequestRateLimitTests(unittest.TestCase):
    def test_sensitive_and_mutating_routes_receive_scoped_limits(self):
        self.assertEqual(rule_for_request("POST", "/api/v1/auth/register").scope, "auth.register.ip")
        self.assertEqual(
            rule_for_request("POST", "/api/v1/communities/abc/invitations").scope,
            "community.invitations.ip",
        )
        self.assertEqual(
            rule_for_request("DELETE", "/api/v1/hosting-connections/abc").scope,
            "hosting.connections.ip",
        )
        self.assertIsNone(rule_for_request("GET", "/api/v1/communities"))

    @patch("twe.rate_limits.execute")
    @patch("twe.rate_limits.fetch_one")
    def test_request_over_limit_is_rejected_with_retry_window(self, fetch_mock, _execute_mock):
        fetch_mock.return_value = {"request_count": 3, "retry_after": 42}

        allowed, retry_after = consume_request_limit(
            object(), RateLimitRule("test", 2, 60), "hashed-identifier",
        )

        self.assertFalse(allowed)
        self.assertEqual(retry_after, 42)


if __name__ == "__main__":
    unittest.main()
