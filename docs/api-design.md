# TWE API Design

## Purpose

This document defines the initial application programming interface for Troglodyte Works Experience.

The API exposes documented business objects and workflows to the web interface and future clients.

The API must follow:

- `docs/database-schema.md`
- `docs/glossary.md`
- `docs/server-operation-lifecycle.md`
- `docs/codex-guidelines.md`

The API should not introduce undocumented business entities or relationships.

---

# Design Principles

- Use clear resource-oriented routes.
- Use JSON for requests and responses.
- Require authentication for private resources.
- Verify authorization for every protected action.
- Use stable internal identifiers in routes.
- Use slugs for human-readable navigation where appropriate.
- Return useful errors without exposing secrets or internal credentials.
- Buttons request Server Operations; they do not invoke scripts directly.
- Initial implementation should remain simple and support the first vertical slice.

---

# Base Path

```text
/api/v1
