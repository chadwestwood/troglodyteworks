import hashlib
import json
import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.integration_database import load_integration_config
from twe.db import Database, execute, fetch_one
from twe.security import hash_password
from twe.services.knowledge_rail import (
    KnowledgeRail,
    KnowledgeRailError,
    embed_text,
    vector_literal,
)


class KnowledgeRailIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database(load_integration_config().database_url)
        try:
            with cls.db.connect() as conn:
                extension = fetch_one(
                    conn,
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'",
                )
                if not extension:
                    raise RuntimeError("pgvector migration is missing")
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL pgvector unavailable: {exc.__class__.__name__}")

    def setUp(self):
        self.suffix = secrets.token_hex(8)
        with self.db.connect() as conn:
            self.member = self._user(conn, "member")
            self.outsider = self._user(conn, "outsider")
            self.community = fetch_one(
                conn,
                """
                INSERT INTO communities (name, slug, created_by)
                VALUES (%s, %s, %s)
                RETURNING id::text
                """,
                (
                    f"Knowledge {self.suffix}",
                    f"knowledge-{self.suffix}",
                    self.member["id"],
                ),
            )
            execute(
                conn,
                """
                INSERT INTO community_memberships (user_id, community_id, role)
                VALUES (%s, %s, 'member')
                """,
                (self.member["id"], self.community["id"]),
            )
            self.global_source = self._source(
                conn,
                f"global-{self.suffix}",
                None,
                "Restart requires confirmation and instance.restart permission.",
            )
            self.private_source = self._source(
                conn,
                f"private-{self.suffix}",
                self.community["id"],
                "Secret alpha maintenance procedure for this Community.",
            )
        self.rail = KnowledgeRail(self.db)

    def tearDown(self):
        with self.db.connect() as conn:
            execute(
                conn,
                "DELETE FROM knowledge_sources WHERE source_key IN (%s, %s)",
                (self.global_source, self.private_source),
            )
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(
                conn,
                "DELETE FROM users WHERE email IN (%s, %s)",
                (self.member["email"], self.outsider["email"]),
            )

    def test_global_and_member_scoped_retrieval_with_citations(self):
        member_result = self.rail.search(
            {"user_id": self.member["id"]},
            "secret alpha maintenance procedure",
        )
        member_keys = {
            result["citation"]["source_key"] for result in member_result["results"]
        }
        self.assertIn(self.private_source, member_keys)
        private = next(
            result
            for result in member_result["results"]
            if result["citation"]["source_key"] == self.private_source
        )
        self.assertEqual(private["scope"]["community_id"], self.community["id"])
        self.assertIn("#procedure", private["citation"]["uri"])

        outsider_result = self.rail.search(
            {"user_id": self.outsider["id"]},
            "secret alpha maintenance procedure",
        )
        outsider_keys = {
            result["citation"]["source_key"] for result in outsider_result["results"]
        }
        self.assertNotIn(self.private_source, outsider_keys)
        self.assertIn(self.global_source, outsider_keys)

    def test_explicit_inaccessible_scope_is_hidden(self):
        with self.assertRaises(KnowledgeRailError) as error:
            self.rail.search(
                {"user_id": self.outsider["id"]},
                "maintenance",
                community_id=self.community["id"],
            )
        self.assertEqual(error.exception.code, "NOT_FOUND")
        self.assertIn("scope was not found", str(error.exception))

    def _user(self, conn, label):
        return fetch_one(
            conn,
            """
            INSERT INTO users (email, password_hash, display_name)
            VALUES (%s, %s, %s)
            RETURNING id::text, email
            """,
            (
                f"{label}-{self.suffix}@example.test",
                hash_password("password123"),
                label,
            ),
        )

    def _source(self, conn, source_key, community_id, content):
        source = fetch_one(
            conn,
            """
            INSERT INTO knowledge_sources
                (source_key, title, source_uri, source_type, community_id,
                 approved, content_sha256, metadata)
            VALUES (%s, %s, %s, 'integration-test', %s, true, %s, %s::jsonb)
            RETURNING id::text
            """,
            (
                source_key,
                source_key,
                f"https://example.test/{source_key}",
                community_id,
                hashlib.sha256(content.encode()).hexdigest(),
                json.dumps({"test": True}),
            ),
        )
        execute(
            conn,
            """
            INSERT INTO knowledge_chunks
                (source_id, chunk_index, heading, anchor, content,
                 token_count, embedding)
            VALUES (%s, 0, 'Procedure', 'procedure', %s, %s, %s::vector)
            """,
            (
                source["id"],
                content,
                len(content.split()),
                vector_literal(embed_text(f"{source_key} Procedure {content}")),
            ),
        )
        return source_key


if __name__ == "__main__":
    unittest.main()
