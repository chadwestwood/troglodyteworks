# Server Operation Lifecycle

## Purpose

This document defines the lifecycle of a Server Operation (SO).

A Server Operation represents the execution of a deterministic capability against a specific Game Instance.

The purpose of this document is to ensure that all Server Operations behave consistently regardless of game or management adapter.

---

# Philosophy

A button does not execute work directly.

A button creates a Server Operation.

The Server Operation is responsible for:

- executing work
- verifying results
- recording progress
- logging outcomes
- reporting success or failure

This creates a reliable audit trail and allows operations to be monitored, retried, or automated.

---

# General Workflow

Capability Requested

↓

Create Server Operation

↓

Queue Operation

↓

Execute Capability

↓

Run Health Checks

↓

Record Result

↓

Complete or Fail

---

# Lifecycle States

## Requested

The operation has been created.

No work has begun.

---

## Queued

The operation is waiting to execute.

---

## Executing

The capability is actively running.

---

## Verifying

Execution has completed.

TWE is confirming that the expected outcome has occurred.

---

## Completed

All verification checks passed.

The operation is considered successful.

---

## Failed

Execution or verification failed.

The failure must include diagnostic information.

---

## Cancelled

The operation was cancelled before completion.

---

# Restart Example

Capability

Restart Instance

↓

Create SO

↓

Stop Instance

↓

Verify Process Stopped

↓

Start Instance

↓

Verify Process Running

↓

Verify Network Port

↓

Verify Game Query

↓

Mark Completed

---

# Health Checks

Health checks are deterministic.

Health checks do not require AI.

Health checks should be specific to the management adapter when necessary.

Examples include:

- expected process exists
- expected process stopped
- expected network port responds
- game query succeeds
- server is broadcasting
- player count available
- configuration loaded
- save directory accessible

---

# Failure Handling

If any health check fails:

- stop further verification
- record the failed stage
- record available diagnostics
- mark the operation as Failed

The operation should never report success unless all required verification passes.

---

# Logging

Every Server Operation should record:

- operation id
- capability
- target instance
- requesting user
- start time
- completion time
- duration
- lifecycle state changes
- health check results
- final outcome

---

# AI Usage

Routine Server Operations should not require AI.

Examples:

- restart
- stop
- start
- backup
- restore
- save
- status

These should execute using deterministic workflows.

AI may assist after failure.

Examples:

- explain log output
- summarize diagnostics
- recommend corrective actions
- compare configuration changes

AI should support operators.

AI should not replace deterministic automation.

---

# Future Considerations

Future versions of TWE may include:

- scheduled Server Operations
- recurring maintenance
- queued operations
- operation dependencies
- rollback procedures
- progress reporting
- distributed execution
- multiple management adapters
- operation templates

---

# Design Principle

A successful Server Operation is not defined by whether a command executed.

A successful Server Operation is defined by whether the desired outcome has been verified.
