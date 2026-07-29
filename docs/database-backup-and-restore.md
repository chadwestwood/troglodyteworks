# Database Backup and Recovery

**Status:** Current production runbook  
**Owner:** Platform administrator  
**Applies to:** Railway PostgreSQL production data  
**Last drill:** 2026-07-29

## Recovery objectives

- **Target recovery point:** no more than 24 hours of data loss for ordinary
  incidents.
- **Target recovery time:** restore and validate service within 2 hours.
- Before a risky migration or bulk data operation, create and retain a manual
  Railway backup.

## Backup approach and retention

The production database is stored on the PostgreSQL service's Railway volume.
Railway volume backups are the primary recovery copy. The PostgreSQL service
has all three schedules enabled:

| Schedule | Railway retention |
| --- | --- |
| Daily | 6 days |
| Weekly | 1 month |
| Monthly | 3 months |

Railway backups are incremental copy-on-write snapshots. A manual backup can be
created before a high-risk change. A particularly important backup may be
locked to prevent normal expiration.

For public beta, verify the three schedules and the timestamp of the newest
successful backup weekly. A green deployment does not prove that a backup is
usable.

The first manual recovery point under this policy was created successfully on
2026-07-29 before the controlled restore drill.

## Railway volume recovery

1. Stop write-producing maintenance work and record the incident time.
2. Open the PostgreSQL service in Railway, then open **Backups**.
3. Select the newest backup from before the incident and choose **Restore**.
4. Review Railway's staged change before deploying it. Railway mounts a new
   restored volume and retains the previous volume unmounted.
5. Deploy the staged restore.
6. Verify:
   - `/health` reports `ok`;
   - `schema_migrations` contains the expected current migrations;
   - a Community, member, World, Discord connection, and provider connection
     known to predate the backup are present;
   - Google sign-in succeeds;
   - the Discord worker connects and a read-only Trog command succeeds.
7. Keep the displaced volume until the recovery is accepted. Record only
   timestamps, backup identity, validation results, and operator—not customer
   data or credentials.

Railway warns that restoring a volume removes backups newer than the selected
restore point. It retains older backups. Volume backups can be restored only
inside the same Railway project and environment.

## Controlled logical restore drill

Run this from a trusted environment that has PostgreSQL client tools and a
server-provided `DATABASE_URL`:

```text
scripts/postgres_restore_drill.sh
```

The script never updates an application table. It:

1. refuses to run if its isolated `twe_restore_drill` schema already exists;
2. records only row counts from `schema_migrations` and `communities`;
3. creates a custom-format logical backup of that verification table;
4. deletes and restores only the verification table;
5. checks the restored result; and
6. removes the temporary schema and dump on success or failure.

Successful output is:

```text
Restore drill passed: the isolated verification table was backed up, deleted, restored, and validated.
```

## Drill record

On 2026-07-29, the controlled logical drill was run against Railway PostgreSQL.
The isolated verification table was backed up, deleted, restored, and
validated. The temporary schema and dump were removed. No application table
was written or replaced.

Repeat the drill:

- before accepting external beta-community data;
- after a PostgreSQL major-version or hosting change; and
- at least once per quarter during active operation.

## Point-in-time recovery

Railway also offers PostgreSQL point-in-time recovery (PITR). It restores into
a new sibling PostgreSQL service without touching the source and retains
roughly four weeks of history. Treat enabling PITR as a separate production
change: review the storage and egress cost, enable it from the PostgreSQL
**Backups** tab, wait for its first base backup, and then conduct a forked
restore test before relying on it.

## Safety rules

- Never paste `DATABASE_URL`, dumps, secrets, or customer rows into source
  control, Linear, chat, screenshots, or logs.
- Never test a restore by replacing the live production volume.
- Never delete the previous volume until application and Discord checks pass.
- A schema-only or synthetic local test does not replace a Railway recovery
  drill.
