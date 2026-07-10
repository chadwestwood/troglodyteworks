# Troglodyte Works Experience Documentation

## Purpose

This directory contains the architectural, engineering, and implementation documentation for Troglodyte Works Experience (TWE).

These documents define the business model, engineering principles, implementation contracts, and development workflow for the project.

Developers and AI implementation agents should begin here before making architectural or implementation decisions.

---

# Documentation Philosophy

Documentation is considered part of the product.

Architecture is intentionally designed before implementation.

Implementation should follow the documented architecture rather than redefining it.

When documentation and implementation disagree:

- pause implementation
- identify the conflict
- update documentation or request clarification
- continue only after the conflict has been resolved

---

# Reading Order

A new contributor should read the documentation in the following order.

## 1. Glossary

```text
glossary.md
```

Defines the shared language used throughout TWE.

This document should be read first.

---

## 2. Database Schema

```text
database-schema.md
```

Defines the business entities and relationships.

This is the source of truth for the application's object model.

---

## 3. Authentication

```text
authentication.md
```

Defines authentication, authorization, Community Membership, roles, and permissions.

---

## 4. API Design

```text
api-design.md
```

Defines the REST API contract exposed by TWE.

---

## 5. Server Operation Lifecycle

```text
server-operation-lifecycle.md
```

Defines deterministic execution and verification of Server Operations.

---

## 6. Engineering Tracker

```text
engineering-tracker.md
```

Defines how engineering work is managed inside TWE.

---

## 7. Codex Guidelines

```text
codex-guidelines.md
```

Defines expectations for AI implementation agents.

Implementation agents should follow this document throughout development.

---

## 8. Vertical Slices

```text
vertical-slices/
```

Defines complete implementation contracts for individual workflows.

The first implementation target is:

```text
citw-genesis-v1.md
```

---

# Project Management

Project planning documents are maintained separately.

Examples:

```text
Meetings/
```

Current documents include:

- PM0001
- PM0002
- PM0003
- PM0004

These documents capture planning discussions and architectural evolution.

Implementation contracts belong inside `/docs`.

---

# Documentation Categories

## Architecture

Defines the business model.

Current documents:

- glossary.md
- database-schema.md
- authentication.md
- api-design.md

---

## Operations

Defines deterministic management behavior.

Current documents:

- server-operation-lifecycle.md

---

## Engineering

Defines project workflow.

Current documents:

- engineering-tracker.md
- codex-guidelines.md

---

## Vertical Slices

Defines production implementation targets.

Current documents:

- vertical-slices/citw-genesis-v1.md

---

# Source of Truth

When conflicts exist, use the following order of precedence.

1. Architecture Decision Records (future)
2. Glossary
3. Database Schema
4. Authentication
5. API Design
6. Server Operation Lifecycle
7. Vertical Slice
8. Existing Implementation

If implementation conflicts with documentation:

Update the documentation or request clarification before continuing.

---

# Development Workflow

TWE follows a documentation-first engineering process.

The expected workflow is:

```text
Idea

↓

Discussion

↓

Documentation

↓

Review

↓

Implementation

↓

Testing

↓

Deployment

↓

Iteration
```

The implementation should always follow the documented design.

---

# AI Development Philosophy

AI implementation agents assist development.

They do not redefine product architecture.

Responsibilities:

Human designers:

- product vision
- architecture
- business rules
- documentation
- final approval

AI implementation agents:

- implementation
- refactoring
- testing
- documentation updates
- migration generation
- repetitive engineering tasks

---

# Long-Term Vision

TWE is designed as a platform.

Current domains include:

- Community
- Hosting
- Engineering
- Platform

Future domains may be added as the platform evolves.

The architecture should encourage extension without requiring redesign.

---

# Final Principle

Every feature should strengthen the architecture.

Every document should reduce ambiguity.

Every implementation should follow the documented design.
