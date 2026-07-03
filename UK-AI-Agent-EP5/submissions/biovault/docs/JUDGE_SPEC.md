# BioVault Judge Spec

## Product Contract

BioVault is lineage-secured memory for AI science agents. It governs AI-generated scientific artifacts, such as Phase II readiness memos, by enforcing source-lineage access, revocation propagation, and audit before content reaches any model.

This submission is a hackathon prototype for the BasedAI Enterprise Memory Governance at Scale track. It is not production security, not clinical decision support, not full Hirebase integration, and not real external connector sync.

## Core Invariants

- Identity is token-bound; `user_id` query/body values do not decide identity.
- Permission checks are server-side.
- No LLM/model call is in the permission path.
- Derived artifacts require a target read grant plus read grants for every included transitive source.
- Redacted/declassified derivatives are explicit governed exceptions with attestation/source hashes.
- Revoked/quarantined sources deny downstream reads.
- Denied reads and `/query` calls return no plaintext/context.
- Every access decision is audited with `request_id`, provenance, and latency.

## A/B/C Policy Semantics

- A = default semantic rule: source-lineage access is required.
- B = future optimization: compile/cache an effective strictest policy without changing A.
- C = exception path: governed redacted/declassified derivatives requiring explicit authority, attestation, hashes, and audit.

## BasedAI Requirement Mapping

| Requirement | BioVault implementation | Evidence | Honest scope |
|---|---|---|---|
| Source ACL/revocation sync | Simulated source ACL/revocation event revokes `adverse_event_memo` and quarantines descendants | `test_stale_capability_denied_after_source_revoke`; demo revoke flow | Simulated source ACL/revocation event, not real external IAM sync |
| Deterministic retrieval-layer enforcement | `GET /artifacts/{id}` and `POST /query` use the same server-side permission gate before returning content | `evaluate_access()`, `can_access()`, `test_allow_deny_matrix` | Deterministic Python/SQL prototype path |
| No LLM in permission path | Permission decisions use token resolution, capability grants, lineage, revocation state, and audit only | Static verifier scan; backend permission tests | Optional model use is only after authorization |
| Audit logs with structured provenance | Access decisions include `request_id`, principal, artifact, operation, reason, latency, and structured detail | `test_artifact_read_audit_contains_structured_detail`; `test_audit_records_all_operation_types` | Regulatory-style traceability, not tamper-evident compliance-grade audit |
| P99 under 200ms local benchmark | Permission latency is benchmarked locally and exposed through metrics | `test_permission_latency_p99_under_200ms`; `/metrics/permission-latency` | Local hackathon benchmark, not production load test |
| Derived memory lineage | Default derived reads require the target artifact read grant plus read grants on every included transitive source | `test_derived_artifact_requires_included_source_grants`; lineage API | Prototype lineage graph; compiled policy cache is future optimization only |
| Source revocation propagation | Revoking a source quarantines descendants derived from that source | `test_multi_level_revocation_propagation`; `test_adverse_event_revocation_quarantines_phase2_memo` | Simulated revocation event, not real external connector sync |
| Open-weight compatibility | The permission layer is model-free and can gate context before any open-weight runtime receives content | `/query` gate; no closed-model runtime dependency | Open-weight compatible, not deeply integrated with a model runtime |
| Bonus temporal expiry | Grants can expire through `expires_at` checks | `test_expired_grant_denies_artifact_read` | Minimal grant-expiry evidence, not a full policy calendar engine |
| Bonus query-time gate/no plaintext on deny | `/query` denies before context/plaintext is returned | `test_cro_query_denied_returns_no_plaintext` | Deterministic query gate, not full semantic inference prevention |

## Demo Contract

- Regulatory Lead can read the Phase II memo before revocation.
- External CRO is denied.
- `adverse_event_memo` revoke quarantines the Phase II memo and descendants.
- Reads after revoke are denied.
- Audit row exposes `request_id` and provenance.

## Known Limitations

- Prototype only.
- Local/ephemeral SQLite.
- Simulated ACL/revocation event, not real connector sync.
- Not production security.
- Not clinical decision support.
- Not full Hirebase integration.
- No production KMS/HSM.
- No tamper-evident audit ledger yet.
