# Memory Architecture Note

## Current V1 position

Lighthouse V1 uses deterministic memory and journal structures for auditability, operational recall, and future dataset preparation.

Memory is not authority.

## Deterministic memory role

Deterministic memory should preserve:

- exact records
- evidence
- timestamps
- outcomes
- schema validation
- audit trails
- unresolved-case tracking

## Future semantic memory role

A future semantic memory layer may help with:

- similarity search
- related-case discovery
- meaning-based recall
- "this resembles a previous issue" support

It must not:

- authorize actions
- overwrite deterministic records
- decide truth
- bypass policy
- override telemetry evidence
- override Operator confirmation
- override the Tool Registry
- override the Permission or Autorun Gate

## Roadmap

```text
V1: deterministic memory only
V1.5: memory schema and lifecycle hardening
V2: optional local semantic retrieval over approved memory records
V2.5: semantic project/file/search memory for Lighthouse Navigator
V3: educational memory layer
```

## Core rule

```text
Semantic memory improves recall.
Deterministic memory preserves truth.
Lighthouse safety remains outside both.
```
