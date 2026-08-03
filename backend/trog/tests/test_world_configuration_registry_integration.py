import secrets
import unittest
import uuid

import psycopg

from tests.integration_database import load_integration_config


class WorldConfigurationRegistryIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            config = load_integration_config()
            self.conn = psycopg.connect(config.database_url)
        except Exception as exc:
            raise unittest.SkipTest(
                f"PostgreSQL unavailable for configuration registry integration test: {exc}"
            )
        suffix = secrets.token_hex(6)
        with self.conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (email,password_hash,display_name) VALUES (%s,'x','Owner') RETURNING id",
                (f"registry-{suffix}@example.test",),
            )
            user_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO communities (name,slug,created_by) VALUES ('Registry Test',%s,%s) RETURNING id",
                (f"registry-{suffix}", user_id),
            )
            community_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO provider_connections
                    (community_id,provider_key,display_name,auth_strategy,status)
                VALUES (%s,'nitrado','Nitrado','configuration','active') RETURNING id
                """,
                (community_id,),
            )
            self.connection_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO provider_resources
                    (provider_connection_id,resource_type,external_resource_id,
                     display_name,available)
                VALUES (%s,'game_server_service','111111','World A',true) RETURNING id
                """,
                (self.connection_id,),
            )
            self.resource_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO provider_resources
                    (provider_connection_id,resource_type,external_resource_id,
                     display_name,available)
                VALUES (%s,'game_server_service','222222','World B',true) RETURNING id
                """,
                (self.connection_id,),
            )
            self.other_resource_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO game_servers
                    (community_id,name,slug,game_type,management_adapter,provider_resource_id)
                VALUES (%s,'Server A',%s,'ARK','nitrado',%s) RETURNING id
                """,
                (community_id, f"server-{suffix}", self.resource_id),
            )
            server_id = cursor.fetchone()[0]
            self.server_id = server_id
            cursor.execute(
                """
                INSERT INTO game_instances
                    (game_server_id,name,slug,instance_type,game_identifier,status)
                VALUES (%s,'World A','world-a','ark_map','WorldA','online') RETURNING id
                """,
                (server_id,),
            )
            self.instance_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO game_instances
                    (game_server_id,name,slug,instance_type,game_identifier,status)
                VALUES (%s,'World A Two','world-a-two','ark_map','WorldATwo','online') RETURNING id
                """,
                (server_id,),
            )
            self.other_instance_id = cursor.fetchone()[0]

    def tearDown(self):
        if hasattr(self, "conn"):
            self.conn.rollback()
            self.conn.close()

    def _insert_revision(self, *, instance_id=None, resource_id=None, external_id="111111"):
        revision_id = uuid.uuid4()
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO world_configuration_revisions
                    (id,game_instance_id,provider_resource_id,provider_connection_id,
                     provider_key,external_resource_id,observed_at,parser_version,
                     snapshot_hash,validation_state)
                VALUES (%s,%s,%s,%s,'nitrado',%s,now(),'test',%s,'verified')
                """,
                (
                    revision_id,
                    instance_id or self.instance_id,
                    resource_id or self.resource_id,
                    self.connection_id,
                    external_id,
                    "sha256:" + secrets.token_hex(32),
                ),
            )
        return revision_id

    def test_promotes_only_a_verified_revision_for_the_same_instance(self):
        revision_id = self._insert_revision()
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO world_configuration_current_revisions
                    (game_instance_id,revision_id)
                VALUES (%s,%s)
                """,
                (self.instance_id, revision_id),
            )
            cursor.execute("SAVEPOINT cross_instance")
            with self.assertRaises(psycopg.Error):
                cursor.execute(
                    """
                    INSERT INTO world_configuration_current_revisions
                        (game_instance_id,revision_id)
                    VALUES (%s,%s)
                    """,
                    (self.other_instance_id, revision_id),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT cross_instance")

    def test_rejects_revision_from_a_different_provider_resource(self):
        with self.conn.cursor() as cursor:
            cursor.execute("SAVEPOINT wrong_resource")
            with self.assertRaises(psycopg.Error):
                self._insert_revision(
                    resource_id=self.other_resource_id,
                    external_id="222222",
                )
            cursor.execute("ROLLBACK TO SAVEPOINT wrong_resource")

    def test_old_current_revision_cannot_be_repromoted_after_provider_rebind(self):
        revision_id = self._insert_revision()
        with self.conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO world_configuration_current_revisions (game_instance_id,revision_id) VALUES (%s,%s)",
                (self.instance_id, revision_id),
            )
            cursor.execute(
                "UPDATE game_servers SET provider_resource_id = %s WHERE id = %s",
                (self.other_resource_id, self.server_id),
            )
            cursor.execute("SAVEPOINT stale_revision")
            with self.assertRaises(psycopg.Error):
                cursor.execute(
                    """
                    INSERT INTO world_configuration_current_revisions
                        (game_instance_id,revision_id)
                    VALUES (%s,%s)
                    ON CONFLICT (game_instance_id) DO UPDATE
                    SET revision_id = EXCLUDED.revision_id
                    """,
                    (self.instance_id, revision_id),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT stale_revision")


if __name__ == "__main__":
    unittest.main()
