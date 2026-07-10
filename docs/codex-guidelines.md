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

When implementing TWE, use the following order of precedence:

1. Architecture Decisions
2. Database Schema
3. Glossary
4. Server Operation Lifecycle
5. Engineering Tracker
6. Project documentation
7. Existing codebase

If conflicts exist, do not guess.

Document the conflict and request clarification.

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
