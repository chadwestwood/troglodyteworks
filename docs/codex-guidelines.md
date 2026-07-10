# Codex Development Guidelines

## Purpose

This document defines the expectations for AI implementation agents contributing to the Troglodyte Works Experience (TWE) project.

Codex is responsible for implementation, not product or architectural decision making.

When uncertainty exists, preserve the documented architecture and request clarification rather than inventing new business rules.

---

# Core Philosophy

Humans design.

AI implements.

Humans review.

Architecture is intentional.

Implementation should faithfully follow the documented design.

---

# Source of Truth

The documentation hierarchy defined in `docs/README.md` is authoritative.

At the current stage, use this order of precedence:

1. Architecture Decision Records, when present
2. Glossary
3. Database Schema
4. Authentication
5. API Design
6. Server Operation Lifecycle
7. Vertical Slice
8. Existing Implementation

Supporting documents such as the Engineering Tracker and Codex Guidelines govern workflow but do not override the business and implementation contracts above.

If conflicts exist, do not guess.

Document the conflict and request clarification.
---
# Implementation Prompts

Implementation prompts should reference the project documentation rather than restating it.

The documentation is the authoritative source of truth for architecture, business rules, terminology, workflows, and implementation contracts.

Implementation prompts should:

- identify the implementation objective
- reference the relevant documentation
- describe the current milestone
- identify any special constraints or review requirements

Implementation prompts should not duplicate architectural decisions that already exist in the documentation.

If documentation and an implementation prompt conflict, pause implementation and request clarification rather than guessing.

The goal is to maintain a single authoritative source of truth and minimize documentation drift.

---

# Business Rules

Never invent:

- business entities
- database relationships
- user workflows
- permissions
- navigation
- terminology

Only implement documented behavior.

---

# Database

Follow the database schema exactly.

Do not:

- rename entities
- merge entities
- create undocumented relationships
- remove fields without approval

Use PostgreSQL best practices.

Create migrations instead of editing live databases.

---

# Documentation

Documentation is part of the product.

When implementation changes documented behavior:

- update documentation
- or request documentation changes

Documentation should remain synchronized with the implementation.

---

# User Interface

Navigation should reflect the object model.

User

↓

Community

↓

Game Server

↓

Game Instance

↓

Server Operations

Avoid creating pages that bypass this hierarchy.

Users should never have to wonder where they are.

---

# Server Operations

Buttons should not directly execute scripts.

Buttons create Server Operations.

Server Operations:

- execute capabilities
- record progress
- perform verification
- record results

Routine operations should use deterministic workflows.

Avoid introducing AI into deterministic workflows.

---

# AI Usage

Prefer deterministic implementations whenever possible.

Use AI only when it provides clear value.

Appropriate AI uses include:

- diagnostics
- summarization
- planning
- documentation generation
- recommendations

Avoid AI for:

- restarting servers
- checking processes
- health verification
- reading configuration values
- other deterministic tasks

---

# Code Quality

Favor:

- readability
- maintainability
- small components
- explicit naming
- clear separation of concerns

Avoid:

- unnecessary abstraction
- premature optimization
- duplicated logic
- hidden behavior

---

# Vertical Slice Development

Implement one complete workflow at a time.

Prefer:

working login

↓

working community

↓

working instance

↓

working Server Operation

instead of partially implementing many unrelated features.

---

# Error Handling

Fail clearly.

Provide useful diagnostics.

Never silently ignore failures.

Whenever possible:

- identify the failing stage
- record diagnostic information
- preserve audit history

---

# Testing

Every implementation should be testable.

Favor deterministic behavior.

Avoid implementations that require manual inspection to verify correctness.

---

# Security

Never expose:

- passwords
- API secrets
- server credentials
- SSH keys

Use environment variables for configuration.

Validate authorization before executing privileged operations.

---

# Development Philosophy

Build the simplest implementation that satisfies the documented requirements.

Do not implement speculative features.

Future extensibility is valuable.

Premature complexity is not.

---

# Final Principle

Codex is an implementation partner.

Codex should strengthen the architecture, not redefine it.
