# Vertical Slice: Visitor to User (V1)

## Purpose

This document defines the first TWE account-creation and anonymous-exploration vertical slice.

Its purpose is to support the transition from an anonymous Visitor to a registered User without requiring immediate Community Membership.

This slice separates:

- visiting TWE
- creating an account
- signing in
- joining a Community

A User may belong to zero or more Communities.

---

# Goal

A Visitor should be able to:

1. Arrive at Troglodyte Works.
2. Choose to explore without signing in.
3. Choose to sign in.
4. Choose to create an account.
5. Become an authenticated User.
6. Reach My Communities.
7. See an appropriate empty state when they have no Community Memberships.

---

# Core Terms

## Visitor

An anonymous person browsing TWE without an authenticated account session.

A Visitor is not stored as a User record.

## User

A person with a registered TWE account.

A User may belong to zero or more Communities.

## Community Member

A User with an active Community Membership in a specific Community.

Creating an account does not automatically create a Community Membership.

---

# User Journey

```text
Troglodyte Works

↓

Welcome

├── Continue to Explore
├── Sign In
└── Create Account
```

Create Account flow:

```text
Create Account

↓

Enter display name, email, and password

↓

Account Created

↓

Authenticated Session Created

↓

My Communities

↓

Community List
or
Empty State
```

---

# Landing Experience

The landing page should present three clear choices:

- Continue to Explore
- Sign In
- Create Account

The interface should not imply that account creation is required to understand what TWE is.

The Visitor should not have to authenticate merely to view public content.

---

# Continue to Explore

Selecting Continue to Explore should open the public exploration experience.

The first version may contain limited content.

Initial public exploration may include:

- TWE purpose
- public product information
- featured or example Communities
- hosting information
- public documentation or announcements

Public exploration must not expose:

- private Communities
- private Game Servers
- private Game Instances
- Server Operation history
- member-only activity
- infrastructure details

The first implementation may use placeholder public content while preserving the navigation path.

---

# Sign In

The existing sign-in flow remains available to registered Users.

Successful sign-in should:

1. Authenticate the User.
2. Create a secure server-managed session.
3. Redirect the User to the intended destination when one exists.
4. Otherwise redirect the User to My Communities.

A User following an invite or deep link should return to that destination after authentication when permitted.

---

# Create Account

The account-creation form should request:

- display name
- email address
- password
- password confirmation

The interface should use the phrase:

```text
Create Account
```

It should not use:

```text
Create User
```

`User` is the internal domain term.

`Account` is the user-facing term.

---

# Account-Creation Rules

Creating an account should:

- create one User record
- store a secure password hash
- create an authenticated session
- sign the User in automatically
- redirect the User to an invite destination when applicable
- otherwise redirect the User to My Communities

Creating an account should not automatically:

- create a Community
- create a Community Membership
- create a Game Server
- create a Game Instance
- grant an owner role
- subscribe the User to hosting

---

# Account Validation

The server must validate:

- display name is present
- email is present
- email format is acceptable
- email is unique
- password meets the approved minimum requirements
- password confirmation matches
- request body contains no unsupported privileged fields

The client may validate for usability.

The server remains authoritative.

---

# Password Requirements

The initial implementation should use a simple, documented minimum standard.

Minimum requirements:

- at least 12 characters
- not entirely whitespace
- must match password confirmation

Do not require arbitrary combinations of uppercase letters, lowercase letters, numbers, and symbols unless a later approved security policy requires them.

Passwords must be hashed using the established TWE password-hashing implementation.

Passwords must never appear in:

- logs
- API responses
- database seed files
- source control
- error messages

---

# Duplicate Email

When the email already belongs to an account, the API should reject registration.

The public response should be useful without exposing unnecessary account information.

Recommended response:

```json
{
    "error": {
        "code": "EMAIL_ALREADY_REGISTERED",
        "message": "An account already exists for that email address."
    }
}
```

The interface should offer navigation to Sign In.

---

# Automatic Sign-In

After successful account creation, TWE should create a secure authenticated session.

The new User should not be forced to enter the same credentials again immediately.

The session should follow the rules defined in:

```text
docs/authentication.md
```

---

# My Communities

After authentication, a User should reach My Communities unless an invite or deep link provides another approved destination.

A User with Community Memberships should see their Community list.

A User with no Community Memberships should see a valid empty state.

---

# Empty My Communities State

The empty state should explain that the account is valid even though the User has not joined a Community.

Suggested content:

```text
You have not joined any Communities yet.
```

Available actions may include:

- Join with an invitation
- Explore public Communities
- Create a Community — future
- Learn about hosting — future

Future actions should be clearly marked when unavailable.

The empty state must not be treated as an error.

---

# Invite-Aware Registration

A Visitor may arrive through an invite link.

The registration flow should preserve the intended destination.

Future flow:

```text
Visitor opens invite

↓

TWE resolves Community and destination

↓

Visitor creates account or signs in

↓

Invite is validated

↓

Community Membership is created

↓

User is taken to the intended destination
```

Invite acceptance is not required for the first implementation unless separately approved.

The first implementation should avoid destroying or ignoring invite destination context where practical.

---

# Navigation Rules

Visitors should always be able to reach:

- Home
- Explore
- Sign In
- Create Account

Authenticated Users should be able to reach:

- My Communities
- Sign Out

A User with zero Communities should not be trapped on an empty page.

They should have a clear path back to Explore.

---

# API Requirements

The first implementation should add:

```text
POST /api/v1/auth/register
```

Request:

```json
{
    "display_name": "Alex",
    "email": "alex@example.com",
    "password": "a-secure-password",
    "password_confirmation": "a-secure-password"
}
```

Successful response:

```json
{
    "user": {
        "id": "user-id",
        "email": "alex@example.com",
        "display_name": "Alex"
    }
}
```

The successful response should also establish the authenticated session cookie.

---

# Registration Processing Requirements

The API must:

- validate the request
- normalize the email address
- reject duplicate email addresses
- hash the password securely
- create the User
- create the authenticated Session
- return the User
- avoid creating Community Memberships automatically
- write an Audit Log entry when required by the current schema

---

# Initial Error Codes

Registration may return:

- `VALIDATION_ERROR`
- `EMAIL_ALREADY_REGISTERED`
- `PASSWORD_MISMATCH`
- `INTERNAL_ERROR`

Errors must follow the standard API error contract defined in:

```text
docs/api-design.md
```

---

# Authorization

Registration is available to Visitors.

Authenticated Users should not normally create a second account from an active session.

Protected Community resources continue to require Community Membership.

Account creation does not grant Community permissions.

---

# Security Requirements

- Use the existing trusted password-hashing implementation.
- Use parameterized database access.
- Rate-limit repeated registration attempts when supported.
- Do not trust client-supplied roles or membership fields.
- Do not allow registration to create an owner or admin role.
- Create secure server-managed sessions.
- Use HTTPS for public registration.
- Do not expose password hashes.
- Do not log raw passwords.

---

# User Interface Requirements

The interface should include:

- a Create Account page
- a visible link between Sign In and Create Account
- a Continue to Explore path
- clear validation messages
- a successful redirect after registration
- a My Communities empty state
- a path from the empty state back to Explore

The interface should prioritize clarity over density.

---

# Tests

At minimum, test:

- successful registration
- automatic sign-in after registration
- duplicate email rejection
- password mismatch rejection
- short-password rejection
- normalized email handling
- User created with zero Community Memberships
- unauthenticated registration access
- authenticated Community routes still require Membership
- empty My Communities response
- session cookie creation
- standard API error structure

---

# Success Criteria

This vertical slice is complete when:

- a Visitor can continue to public exploration
- a Visitor can open Create Account
- a Visitor can create a valid account
- the new User is signed in automatically
- the new User can open My Communities
- a User with zero Communities sees a useful empty state
- creating an account does not create a Community or Membership
- the User can navigate back to Explore
- all data persists in PostgreSQL

---

# Out of Scope

This document does not define:

- Community creation
- invite acceptance implementation
- public Community discovery search
- email verification
- password reset
- multi-factor authentication
- Discord authentication
- Google authentication
- subscriptions
- hosting purchases
- profile editing
- account deletion
- moderation policy

---

# Related Documentation

This document should be interpreted together with:

```text
docs/glossary.md
docs/database-schema.md
docs/authentication.md
docs/api-design.md
docs/codex-guidelines.md
```

The documentation precedence defined in:

```text
docs/README.md
```

remains authoritative.

---

# Final Principle

A TWE account establishes identity.

Community Membership establishes belonging.

Creating an account must not force the User into a Community or require them to stop exploring.