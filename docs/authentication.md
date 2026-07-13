# TWE Authentication and Authorization

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
- Begin with the simplest secure implementation needed for the first vertical slice.
- Do not add public registration, external login providers, or account recovery until they are approved.

---

# Authentication Model

TWE will initially use:

- email address
- password
- secure server-managed session
- HTTP-only session cookie

The browser should not store raw passwords or long-lived authentication credentials.

---

# User Account

A User represents a person with a TWE account.

Initial fields are defined in `docs/database-schema.md`.

Required authentication fields:

- id
- email
- password_hash
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

Accepting an invitation creates only Community Membership. It does not grant Game Instance access, Discord installation approval, Server Operations, restart, save, mods, or ownership.
