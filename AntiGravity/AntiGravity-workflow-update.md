# AntiGravity Workflow Update

## Purpose

This document records how Lighthouse should use AntiGravity after the AG-001 and AG-002 review passes.

## Current AntiGravity status

AntiGravity produced useful review output for:

- AG-001: external codebase review
- AG-002: evidence verification report

AntiGravity quota was reached before AG-003 could be performed by AntiGravity.

## Workflow rule

AntiGravity should be treated as a quota-constrained reviewer, not as an always-available build agent.

The AntiGravity CLI should not be treated as a quota bypass until proven otherwise.

SDK/API usage is deferred until there is a cost-controlled, high-value use case.

## Write policy

Do not allow AntiGravity to write to the Lighthouse repository unless all of the following are true:

- the task is narrow
- the target files are explicitly listed
- the expected output is known
- the result can be reviewed before merge
- the change is consistent with the Lighthouse safety model

## Recommended AntiGravity use cases

Useful AntiGravity tasks:

- independent codebase review
- evidence verification
- adversarial test-design review
- architecture critique
- documentation review
- verification of claims made in reports

Avoid using AntiGravity for:

- broad autonomous feature implementation
- dependency installation
- MCP implementation before design approval
- repository-wide rewrites
- security-sensitive changes without a strict scope
- quota-bypass experiments

## Relationship to Lighthouse build thread

The primary build thread remains the source of truth for:

- implementation sequence
- PR decisions
- test results
- merge decisions
- V1 architecture boundaries

AntiGravity outputs should be imported back into the primary build thread as review evidence, not as independent authority.

## MCP note

Future Frontier-model communication should be considered through a controlled MCP architecture with explicit approval boundaries.

MCP dependencies should be added only when the MCP layer is intentionally designed and implemented.
