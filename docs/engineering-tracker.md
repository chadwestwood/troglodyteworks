# TWE Engineering Tracker

## Purpose

The Engineering Tracker is the central system for managing the ongoing development of Troglodyte Works Experience (TWE).

Every engineering effort is represented as an Issue.

Issues are categorized by type, prioritized, assigned, documented, and tracked through completion.

The Engineering Tracker is intended to replace scattered notes, emails, and TODO lists with a unified engineering workflow.

---

# Design Philosophy

The tracker manages work, not code.

Code is the result of engineering work.

Documentation, planning, research, bugs, and features all exist as first-class engineering items.

---

# Issue Types

## Bug

Something that previously worked or should work but currently does not.

Examples

- Genesis status reports Offline while server is running.
- Login page fails after successful authentication.

---

## Improvement (IMP)

The software works correctly.

A better design or workflow has been identified.

Examples

- Community page should display recent activity.
- Improve onboarding after accepting an invite.

---

## Feature

A completely new capability.

Examples

- Discord authentication
- Scheduled backups
- Community event calendar

---

## Research

Investigation before implementation.

Examples

- Evaluate Steam Query protocol.
- Compare OpenClaw and direct server management.

---

## Documentation

Engineering documentation.

Examples

- Update database schema.
- Revise architecture diagrams.
- Expand glossary.

---

# Issue Status

Draft

Ready

In Progress

Blocked

Testing

Completed

Archived

---

# Priority

Critical

High

Normal

Low

Future

---

# Relationships

Issues may reference:

- Communities
- Game Servers
- Game Instances
- Server Operations
- Documentation
- Database entities

---

# Engineering Workflow

Idea

↓

Issue Created

↓

Discussion

↓

Approval

↓

Implementation

↓

Testing

↓

Release

↓

Closed

---

# Future Automation

Future versions of TWE may allow AI agents to:

- create implementation plans
- generate documentation
- produce SQL migrations
- generate pull requests
- summarize completed work
- recommend duplicate issues
- suggest related documentation

AI assists engineering.

AI does not replace engineering judgment.

---

# Design Goal

The Engineering Tracker should become the primary project management system for TWE itself.

TWE should eventually manage its own development lifecycle.
