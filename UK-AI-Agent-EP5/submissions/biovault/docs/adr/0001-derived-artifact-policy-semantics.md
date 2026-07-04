# ADR 0001: Derived Artifact Policy Semantics

## Status

Accepted for the official BioVault hackathon submission.

## Context

BioVault stores source and derived scientific artifacts for AI science agents. A derived artifact can include sensitive source content. A principal may have a read grant on the derived artifact while lacking read grants on one or more included sources. If that read were allowed, the derived artifact could disclose source content outside the source permissions.

The prototype also supports governed redaction, where a new artifact can explicitly exclude a parent source and record that exclusion with attestation metadata and source hashes.

## Decision

BioVault enforces derived artifact reads using these semantics:

1. The principal must have a read grant on the target artifact.
2. If the target artifact is derived, the principal must also have read grants on every included transitive source.
3. If any included transitive source is revoked or quarantined, the read is denied with `derived_from_revoked_source`.
4. If any included transitive source grant is missing, the read is denied with `missing_source_lineage_capability`.
5. Redacted-out parents are governed exceptions only when the redaction flow records inclusion state, source hashes, and attestation metadata.
6. `/query` uses the same read path as direct artifact reads, so agent retrieval and UI artifact reads share one enforcement stack.

## Consequences

- A target-artifact grant alone cannot disclose derived source content.
- Revoking a source seals the derived chain consistently across direct artifact reads and `/query`.
- Governed redaction remains possible without letting redaction become a laundering path around revoked or unauthorized sources.
- Read-time lineage checks are simple and auditable for the prototype.
- A compiled effective-policy cache could be added later for scale, but it must preserve the same semantics.

## Non-Goals

- This ADR does not introduce new product features.
- This ADR does not claim production-grade IAM integration, tamper-evident audit, clinical decision support, production load testing, full Hirebase integration, or full semantic inference prevention.
- This ADR does not add model, LLM, payment, remittance, or chain behavior.

## Evidence

- `backend/app/main.py`: `resolve_principal()`, `has_grant()`, `get_included_lineage_parents()`, `evaluate_access()`, `can_access()`, `/query`
- `backend/tests/test_biovault.py`: source-lineage, revocation, redaction, audit, temporal access, and `/query` tests
- `docs/REQUIREMENTS_TRACEABILITY.md`
- `docs/THREAT_MODEL.md`

