# BioVault Requirements Traceability

This matrix maps the official submission claims to implementation evidence, tests, demo evidence, and honest scope. It is intentionally limited to the current BioVault prototype.

| ID | Requirement | Implementation Evidence | Automated Evidence | Demo Evidence | Honest Scope |
|---|---|---|---|---|---|
| R1 | Bearer token is the authority source | `resolve_principal()` hashes the bearer token and protected routes use it before access decisions | `test_user_id_query_param_is_not_authority`, `test_missing_and_invalid_token_denied` | CRO cannot become CEO through query params | Demo token issuance only; not external IAM |
| R2 | Direct artifact capability is required | `has_grant()` checks `(user_id, artifact_id, operation)` | `test_allow_deny_matrix`, `test_unauthorised_grant_denied`, `test_authorised_grant_succeeds` | Regulatory Lead allowed, External CRO denied | Capability model is prototype-local |
| R3 | Derived reads require included transitive source grants | `get_included_lineage_parents()` and `evaluate_access()` check every included parent for read grants | `test_derived_artifact_requires_included_source_grants` | Lineage panel shows included parents for Phase II memo | Direct read-time enforcement, not compiled policy cache |
| R4 | Revoked or quarantined included sources deny derived reads | `evaluate_access()` returns `derived_from_revoked_source`; revoke path quarantines descendants | `test_adverse_event_revocation_quarantines_phase2_memo`, `test_multi_level_revocation_propagation`, `test_stale_capability_denied_after_source_revoke` | Revoking Adverse Event Memo quarantines Phase II memo | Source revocation is simulated, not synced from external IAM |
| R5 | Redacted-out parents are governed exceptions | Redaction flow records inclusion state, source hashes, and attestation metadata | `test_redaction_requires_redact_authority`, `test_redaction_cannot_launder_revoked_source`, `test_governed_redaction_succeeds_on_healthy_sources` | Optional advanced check creates governed redacted artifact | Prototype redaction semantics; not a full declassification workflow |
| R6 | `/query` uses the same read permission path | `/query` calls `can_access(..., "read")` and returns no content on deny | `test_query_audit_contains_structured_detail`, `test_cro_query_denied_returns_no_plaintext` | `scripts/demo_agent_cro.py` shows CRO denied before synthesis | Deterministic gate only; not full semantic inference prevention |
| R7 | Every access decision is audited | `log_audit()` records request ID, decision, reason, latency, and structured detail | `test_audit_records_all_operation_types`, `test_artifact_read_audit_contains_structured_detail` | Audit log expands request provenance | Regulatory-style traceability, not tamper-evident audit |
| R8 | Permission path has no model or LLM call | Backend permission functions use Python/SQL only | Static scan in `scripts/verify_submission.py` | Flow Banner shows permission path before generation | Optional model generation is a hook outside the enforcement path |
| R9 | Permission checks are locally fast enough for demo | Indexed lookup paths and local benchmark endpoint | `test_permission_latency_p99_under_200ms` | UI latency metrics after interactions | Local hackathon benchmark, not production load testing |
| R10 | Temporal grant expiry is represented | `expires_at` is checked in `has_grant()` | `test_expired_grant_denies_artifact_read` | Evidence matrix in UI lists temporal access | Not a full policy calendar engine |
| R11 | Denied responses do not return plaintext | Deny branches omit decrypted content | `test_cro_denial_returns_no_plaintext_content`, `test_cro_query_denied_returns_no_plaintext` | CRO denial panel shows no clinical content | Does not prevent all possible inference from metadata |
| R12 | Submission stays biotech and AI-science focused | README, docs, demo script, and UI use BVK-14 scenario | Static forbidden-language scan in `scripts/verify_submission.py` | Demo uses Phase II readiness, CRO, toxicity, and adverse-event artifacts | Domain framing is demo data, not clinical validation |

## Verification Commands

```powershell
python scripts/verify_submission.py
cd backend
python -m pytest -q
cd ..\frontend
npm run build
```

