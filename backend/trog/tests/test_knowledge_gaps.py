import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.knowledge_gaps import (
    classify_gap,
    dedupe_question,
    sanitize_question,
)


class KnowledgeGapTests(unittest.TestCase):
    def test_sensitive_values_are_removed_before_storage(self):
        sanitized = sanitize_question(
            "Email me at player@example.com using token=abc123 from "
            "https://example.com/private at 10.0.0.103 for <@123456789012345678>."
        )

        self.assertNotIn("player@example.com", sanitized)
        self.assertNotIn("abc123", sanitized)
        self.assertNotIn("10.0.0.103", sanitized)
        self.assertNotIn("123456789012345678", sanitized)
        self.assertIn("[redacted]", sanitized)

    def test_questions_are_classified_for_review(self):
        self.assertEqual(classify_gap("How do I tame a Gigantoraptor?"), "playbook")
        self.assertEqual(classify_gap("Install this mod for me"), "capability")
        self.assertEqual(classify_gap("What tribute summons the Broodmother?"), "knowledge")

    def test_minor_wording_variants_share_a_dedupe_key(self):
        self.assertEqual(
            dedupe_question("Trog, can you tell me how to tame a Gigantoraptor?"),
            dedupe_question("How do I tame the Gigantoraptor?"),
        )


if __name__ == "__main__":
    unittest.main()
