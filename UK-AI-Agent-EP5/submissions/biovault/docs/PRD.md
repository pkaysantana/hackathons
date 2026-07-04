# BioVault PRD

## Summary

BioVault is an educational prototype for lineage-secured artifact memory for AI science agents. It gates access to shared scientific artifacts before any optional model generation. The product focus is biotech R&D memory governance: derived Phase II readiness memos, source revocation, CRO access denial, and auditability.

BioVault is not an AI agent, not a clinical decision-support tool, and not production security software. The permission path is deterministic Python/SQL and has no model or LLM call.

## Audience

| Audience | Need |
|---|---|
| Hackathon judges | Verify the core memory-governance behavior quickly and reproducibly |
| AI science teams | Understand how agents should request authorized scientific context |
| Security reviewers | Inspect the trust boundary, tests, audit records, and honest limitations |
| Demo operators | Run the BVK-14 scenario without changing code or state manually |

## Problem

AI science agents can produce derived artifacts from sensitive sources such as SAR tables, toxicity reports, adverse-event memos, and public target biology. If access control is only applied to the final artifact, a derived memo can disclose source material to a principal that lacks permission to the included sources. If revoked sources are copied into derived outputs, stale derived content can persist after the source is no longer trusted.

BioVault addresses this by making the retrieval layer the enforcement boundary. Agents must call `GET /artifacts/{id}` or `POST /query` before content can reach a model.

## Goals

- Enforce capability grants per `(principal, artifact, operation)`.
- Require a derived artifact read to have both the target artifact grant and read grants on every included transitive source.
- Deny reads when any included source has been revoked or quarantined.
- Preserve governed redaction exceptions only when redacted-out parents have explicit attestation and source hashes.
- Use the same read permission path for `/query` as for direct artifact reads.
- Log every access decision with request ID, principal, operation, reason, latency, and structured provenance.
- Keep the permission path model-free and dependency-light for judge inspection.
- Keep the submission biotech and AI-science focused.

## Non-Goals

- No new product features for this submission evidence pass.
- No changes to auth, grant, redaction, lineage, revocation, scoring, or UI behavior.
- No model, LLM, closed-model, or agent-runtime dependency in the permission path.
- No production security claim, clinical decision-support claim, real external ACL sync, full Hirebase integration, production load test, or full semantic inference prevention claim.
- No live payment, chain, remittance, or settlement execution.

## Core Semantics

1. A bearer token resolves to one principal through `resolve_principal()`.
2. `evaluate_access()` checks artifact existence, artifact status, direct capability grant, lineage health, and source-lineage grants.
3. For derived reads, every included transitive source must be readable by the same principal.
4. Revoked or quarantined included sources deny with `derived_from_revoked_source`.
5. Missing included source grants deny with `missing_source_lineage_capability`.
6. Redacted-out parents are excluded from the included-source grant requirement only when governed redaction metadata records the exception.
7. `/query` calls the same read path and returns no plaintext on deny.

## Demo Acceptance Criteria

| Scenario | Expected Result |
|---|---|
| Regulatory Lead reads Phase II memo | `allow`, plaintext returned |
| External CRO reads Phase II memo | `deny`, no plaintext returned |
| Intern receives only target-artifact grant for Phase II memo | `deny`, missing source-lineage capability |
| Adverse Event Memo is revoked | Phase II memo and descendants quarantine |
| CEO reads Phase II memo after source revocation | `deny`, `derived_from_revoked_source` |
| CRO calls `/query` for Phase II memo | `deny`, no plaintext/context returned |
| Governed redaction excludes a healthy parent | Redaction attestation records included and redacted parents |

## Evidence

- Requirements traceability: `docs/REQUIREMENTS_TRACEABILITY.md`
- Architecture: `docs/ARCHITECTURE.md`
- ADR: `docs/adr/0001-derived-artifact-policy-semantics.md`
- Evaluation harness: `docs/EVALUATION_HARNESS.md`
- Threat model: `docs/THREAT_MODEL.md`
- Submission checklist: `docs/SUBMISSION_CHECKLIST.md`
- Static verifier: `scripts/verify_submission.py`

