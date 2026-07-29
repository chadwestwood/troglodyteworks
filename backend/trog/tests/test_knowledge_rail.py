import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.knowledge_rail import (
    EMBEDDING_DIMENSIONS,
    approved_sources,
    embed_text,
    markdown_chunks,
    vector_literal,
    KnowledgeRail,
    KnowledgeRailError,
)


class KnowledgeRailUnitTests(unittest.TestCase):
    def test_markdown_chunks_preserve_headings_and_citation_anchors(self):
        chunks = markdown_chunks(
            "# Restart server\n\nSummary text.\n\n"
            "## Permission\n\nRequires instance.restart.\n\n"
            "## Failure behavior\n\nFails closed."
        )
        self.assertEqual(
            [(chunk.heading, chunk.anchor) for chunk in chunks],
            [
                ("Restart server", "restart-server"),
                ("Permission", "permission"),
                ("Failure behavior", "failure-behavior"),
            ],
        )
        self.assertIn("instance.restart", chunks[1].content)

    def test_embedding_is_stable_normalized_and_fixed_size(self):
        first = embed_text("restart the Genesis server")
        second = embed_text("restart the Genesis server")
        different = embed_text("create a Community poll")
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(len(first), EMBEDDING_DIMENSIONS)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first)), 1.0)
        self.assertTrue(vector_literal(first).startswith("["))

    def test_manifest_accepts_only_approved_in_directory_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "approved.md").write_text("# Approved\n\nEvidence.", encoding="utf-8")
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sources": [
                            {
                                "source_key": "approved",
                                "title": "Approved",
                                "path": "approved.md",
                                "source_uri": "https://example.test/approved",
                                "source_type": "test",
                                "scope": "global",
                                "approved": True,
                            },
                            {
                                "source_key": "draft",
                                "title": "Draft",
                                "path": "missing.md",
                                "source_uri": "https://example.test/draft",
                                "source_type": "test",
                                "scope": "global",
                                "approved": False,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            sources = approved_sources(manifest)
        self.assertEqual([source["source_key"] for source in sources], ["approved"])

    def test_manifest_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside-knowledge.md"
            outside.write_text("# Outside", encoding="utf-8")
            self.addCleanup(outside.unlink, missing_ok=True)
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sources": [
                            {
                                "source_key": "outside",
                                "title": "Outside",
                                "path": "../outside-knowledge.md",
                                "source_uri": "https://example.test/outside",
                                "source_type": "test",
                                "scope": "global",
                                "approved": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                approved_sources(manifest)

    def test_search_rejects_non_searchable_query_before_database_access(self):
        class UnusedDatabase:
            def connect(self):
                raise AssertionError("database must not be reached")

        with self.assertRaises(KnowledgeRailError) as error:
            KnowledgeRail(UnusedDatabase()).search({"user_id": "unused"}, "???")
        self.assertEqual(error.exception.code, "INVALID_ARGUMENT")


if __name__ == "__main__":
    unittest.main()
