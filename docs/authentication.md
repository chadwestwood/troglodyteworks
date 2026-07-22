# TWE Authentication and Authorization

**Status:** Implemented with known security remediation

**Known findings:** `known-security-work.md`

## Purpose

This document defines how Troglodyte Works Experience identifies users, maintains authenticated sessions, and determines what users are allowed to access or manage.

Authentication answers:

> Who is the user?

Authorization answers:

> What is the user allowed to do?

This document defines the initial rules required for the Cohorts in the Wild Genesis vertical slice.

---

# Design Principles

- Use secure server-managed sessions.
- Store passwords only as strong password hashes.
- Never expose passwords, session secrets, or authentication tokens to client-side code.
- Require authentication for private community resources.
- Authorize every protected request on the server.
- Community access is determined through Community Membership.
- Operation permissions are determined by role and capability.
- Community invitation management is authorized by Community role in V1.
- TWE User is the canonical account; external providers are linked authentication methods.
- Do not automatically merge accounts solely because provider emails match.
- Begin with the simplest secure implementation needed for the active vertical slice.

---

# Authentication Model

TWE supports:

- email address
- password
- Google OAuth/OIDC identity
- Discord OAuth identity
- secure server-managed session
- HTTP-only session cookie

The browser should not store raw passwords or long-lived authentication credentials.

Google and Discord identities are stored in `user_external_identities`. The immutable provider subject is the identity key. Provider email and display name are metadata only. Google OpenID Connect ID tokens are cryptographically verified against Google's published signing keys; issuer, audience, expiration, and nonce must all be valid before an identity is accepted.

---

# User Account

A User represents a person with a TWE account.

Initial fields are defined in `docs/database-schema.md`.

Core user fields:

- id
- email
- password_hash, nullable when the User has only external authentication methods
- display_name
- created_at
- updated_at

Email addresses must be unique.

Passwords must never be stored in plain text.

---

# Password Handling

Passwords must be hashed using an established password-hashing algorithm.

Preferred options:

- Argon2id
- bcrypt

Codex should use the secure default supported by the selected application framework.

Do not create a custom password-hashing implementation.

Password comparison must occur on the server.

Passwords must never appear in:

- logs
- API responses
- database seed files
- source control
- error messages

---

# External Identity and Account Linking

Google and Discord sign-in use provider-neutral external identities. A signed-in User may connect Google or Discord from Account Settings.

Rules:

- login may create a new TWE User when the provider identity is not linked;
- linking never creates a new TWE User;
- link state is bound to the currently signed-in User;
- an identity already linked to the same User is idempotent;
- an identity linked to another User is a conflict;
- users cannot unlink their final usable authentication method;
- Google or Discord email matching an existing TWE email is not proof of ownership.

See:

```text
docs/vertical-slices/multi-provider-authentication-and-account-linking-v1.md
```

---

# Platform Admin Access

Platform admin access is separate from Community roles.

Rules:

- platform admins are configured through `TWE_ADMIN_EMAILS`;
- Community owner/admin/moderator roles do not grant platform admin access;
- the first admin surface is read-only and shows Users and Communities;
- admin endpoints must still require an authenticated TWE session.

---

# Session Model

After successful sign-in, the server creates an authenticated session.

The browser receives a secure session cookie.

The session cookie should use:

- `HttpOnly`
- `SameSite=Lax` or stricter
- `Secure` when served over HTTPS
- a limited expiration time

The session record should identify:

- session id
- user id
- created time
- expiration time
- last activity time, when supported
- revocation time, when applicable

Session identifiers must be random and unguessable.

---

# Sign-In Workflow

```text
User submits email and password

↓

Server finds the User by email

↓

Server verifies the password hash

↓

Server creates an authenticated session

↓

Server returns the current User

↓

Browser receives the secure session cookie
```

---

# Community Invitation Authorization

Community owners, admins, and moderators may create, list, revoke, and approve Community Invitations in V1.

Role safety applies:

- owner may invite admin, moderator, or member;
- admin may invite moderator or member;
- moderator may invite member;
- owner cannot be granted through an invitation.

The role hierarchy must be checked both when an invitation is created and when a
membership request is approved. As of 2026-07-22, the approval-path recheck is a
known security remediation item; this document states the required contract, not
an assertion that the defect has already been fixed.

Accepting an invitation creates only Community Membership. It does not grant Game Instance access, Discord installation approval, Server Operations, restart, save, mods, or ownership.
