# BioVault Threat Model and Security Assumptions

## Scope

This threat model covers the hackathon prototype enforcement boundary: protected artifact reads through `GET /artifacts/{id}` and agent retrieval through `POST /query`.

BioVault is an educational prototype. It is not production security software, not a clinical decision-support system, and not a regulated medical device.

## Assets

| Asset | Why It Matters |
|---|---|
| Capability tokens | Resolve principals and authorize artifact operations |
| Encrypted artifact content | Contains sensitive scientific and clinical-style demo data |
| Lineage edges and source hashes | Determine whether derived artifacts can be disclosed |
| Redaction attestations | Record governed exceptions for excluded parents |
| Audit events | Provide traceability for allow and deny decisions |

## Trust Boundaries

```text
Agent or UI caller
  -> bearer token
  -> FastAPI route
  -> resolve_principal()
  -> evaluate_access()
  -> audit log
  -> decrypt content only on allow
```

The model runtime, if one is used later, is outside the enforcement boundary. It receives content only after BioVault returns an allow decision.

## Key Threats and Mitigations

| Threat | Mitigation in Prototype | Residual Risk |
|---|---|---|
| Caller spoofs principal through query params | Protected routes resolve principal from bearer token | Demo token lifecycle only |
| Principal has target grant but lacks source grants | Derived reads check included transitive source grants | Read-time traversal, not compiled cache |
| Source is revoked after derived memo exists | Revoke path quarantines descendants; reads deny with `derived_from_revoked_source` | Revocation event is simulated |
| Redaction is used to launder revoked content | Redaction requires authority and cannot exclude already revoked parents | Not a full declassification workflow |
| Denied `/query` leaks plaintext to an agent | Denied responses omit plaintext/context | Metadata can still reveal that an artifact exists |
| Permission decision is influenced by a model | Permission path is Python/SQL only | Optional generation is not implemented in repo |
| Audit records are treated as compliance-grade logs | Audit includes request IDs and structured detail | Not tamper-evident or append-only |
| Local benchmark is treated as production performance | Tests measure local P99 only | Not a production load test |

## Security Assumptions

- The backend process and local SQLite database are trusted for the demo.
- Capability tokens are delivered to callers by the demo seed or grant flow.
- Callers treat denied responses as hard stops and do not pass unavailable content to a model.
- Optional model generation, if integrated outside this repo, must call `/query` before using artifact content.
- Demo scientific content is synthetic and not validated for clinical or scientific decision-making.

## Explicit Non-Claims

- No production-grade IAM or key management.
- No real external ACL event sync.
- No full Hirebase integration.
- No tamper-evident compliance audit.
- No clinical decision support or regulated medical functionality.
- No production load test.
- No full semantic inference prevention.
- No live payment, chain, remittance, or settlement execution.

