# TWE Conceptual Data Model

**Status:** Current conceptual summary

**Canonical detail:** `database-schema.md`

This document intentionally summarizes the product model. Table names, fields, constraints, and migration behavior belong in `database-schema.md`.

## Community center

```text
User
  -> Community Membership
  -> Community
       -> Game Server
            -> Game Instance
```

- A User is the canonical TWE account.
- External identities such as Google and Discord are sign-in methods linked to that User.
- Community Membership grants a role inside one Community.
- A Community can exist without any hosted game service.
- A Game Server is the Community's logical game environment.
- A Game Instance is one independently addressable playable environment, such as Genesis.

## Provider boundary

```text
Community
  -> Provider Connection
       -> Provider Resource
            -> Game Server or Game Instance binding
```

Provider credentials are encrypted, revocable, scoped, and never part of the Community identity. Replacing Nitrado, self-hosting, or another provider must not require replacing the Community or its Memberships.

## Discord boundary

```text
Discord Guild Installation
  -> Instance Access Grant
       -> provider Community
       -> exact Game Server and Game Instance
       -> approved read capabilities and channel scope
```

Discord installation, Discord identity, Community Membership, provider approval, and capability grants are separate authorities. A Discord role or browser-supplied identifier is not sufficient authority.

## Operations

Server Operations record requested capabilities, authorization, execution, verification, results, and audit history. Current Nitrado production operations are read-only. Disruptive operations require the reviewed lifecycle in `server-operation-lifecycle.md`.

## Retired model

The earlier `Customer -> Service -> Server` hierarchy is superseded. It treated hosting as the product center and did not adequately model Communities, Memberships, external identities, provider replacement, or Instance-scoped Discord access.
