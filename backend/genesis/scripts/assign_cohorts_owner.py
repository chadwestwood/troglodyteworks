#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import load_config
from twe.db import Database, execute, fetch_one


def normalize_email(value: str) -> str:
    return value.strip().lower()


def main():
    parser = argparse.ArgumentParser(description="Assign an existing User as owner of Cohorts in the Wild.")
    parser.add_argument("--email", required=True, help="Existing User email address.")
    parser.add_argument("--community-slug", default="cohorts-in-the-wild")
    parser.add_argument("--granted-by-email", help="Optional existing User email for audit attribution.")
    args = parser.parse_args()

    result = assign_owner(
        Database(load_config().database_url),
        args.email,
        args.community_slug,
        args.granted_by_email,
    )

    print(f"Assigned owner membership for {result['email']} in {result['community_slug']}.")


def assign_owner(db: Database, email: str, community_slug: str = "cohorts-in-the-wild", granted_by_email: str | None = None):
    normalized_email = normalize_email(email)
    normalized_granted_by = normalize_email(granted_by_email) if granted_by_email else None

    with db.connect() as conn:
        user = fetch_one(conn, "SELECT id::text, email FROM users WHERE lower(email) = %s", (normalized_email,))
        if not user:
            raise SystemExit("User was not found.")

        community = fetch_one(conn, "SELECT id::text, slug FROM communities WHERE slug = %s", (community_slug,))
        if not community:
            raise SystemExit("Community was not found.")

        granted_by = None
        if normalized_granted_by:
            granted_by = fetch_one(conn, "SELECT id::text FROM users WHERE lower(email) = %s", (normalized_granted_by,))
            if not granted_by:
                raise SystemExit("Granting User was not found.")

        membership = fetch_one(
            conn,
            """
            INSERT INTO community_memberships (user_id, community_id, role)
            VALUES (%s, %s, 'owner')
            ON CONFLICT (user_id, community_id) DO UPDATE SET role = 'owner'
            RETURNING id::text, role
            """,
            (user["id"], community["id"]),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
            VALUES (%s, %s, 'admin.community_owner_assigned', 'community_membership', %s,
                    jsonb_build_object('assigned_user_email', %s::text, 'role', %s::text))
            """,
            (
                granted_by["id"] if granted_by else user["id"],
                community["id"],
                membership["id"],
                user["email"],
                membership["role"],
            ),
        )
    return {"email": user["email"], "community_slug": community["slug"], "membership_id": membership["id"]}


if __name__ == "__main__":
    main()
