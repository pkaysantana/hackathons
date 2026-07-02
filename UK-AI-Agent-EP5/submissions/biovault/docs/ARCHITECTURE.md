# BioVault — Architecture

## Overview

BioVault is a deterministic, LLM-free capability enforcement layer that sits between AI agents and a shared artifact store. The model — any open-weight runtime — is outside the enforcement boundary. It only sees content the gate has already authorised.

**The retrieval layer (`GET /artifacts/{id}` and `POST /query`) is the enforcement boundary.** Every agent access decision happens here before any optional model generation.

The demo seed is the **BVK-14 kinase programme** — pharma R&D memory governance for AI science agents.

**Honest prototype scope:** source ACL/revocation events are **simulated** in this MVP (no external IAM sync). Audit logs provide **regulatory-style traceability**, not tamper-evident compliance-grade audit. P99 latency evidence is a **local hackathon benchmark**, not a production load test.

---

## Why this is not secure RAG with role labels

RAG with LLM-based sensitivity filtering:
- Makes every retrieval go through a model to classify the content
- Token-heavy: every retrieval consumes model tokens
- Non-deterministic: the model can be confused, jailbroken, or prompted into surfacing sensitive context
- Has no concept of artifact lineage: revoking a source document does not automatically close access to derived outputs

BioVault's permission path:
- Pure SQL — deterministic, reproducible, auditable
- **Zero model tokens consumed in the permission path**
- Lineage-aware: revoking a source quarantines all derived descendants via BFS propagation
- Every decision logged with a structured `request_id` for traceability

---

## Why global memory avoids duplicated-silo drift

The alternative approach — copying files into per-team folders — breaks governance:

1. Regulatory copies an adverse-event memo into a "board" folder for review.
2. The canonical source is revoked. The copy persists.
3. An external CRO's AI agent retrieves the copy. Clinical data leaks.

BioVault uses one canonical store. Every principal reads the same artifact under their own capability grant. Revoking `adverse_event_memo` propagates through lineage to every derived artifact that included it.

---

## Biotech demo: principals and artifacts

### Principals

| ID | Name | Role | Capability grants |
|---|---|---|---|
| `u_ceo` | Avery Chen | CEO | All ops on all artifacts |
| `u_regulatory` | Nora Singh | Regulatory Lead | `read` on toxicity report, adverse-event memo, Phase II memo |
| `u_research` | Maya Patel | Research Scientist | `read`+`derive` on public paper, SAR table, docking report, toxicity report |
| `u_compchem` | Leo Morgan | Computational Chemist | `read`+`derive` on public paper, SAR table, docking report |
| `u_cro` | Owen Brooks | External CRO Scientist | `read` on public paper, CRO assay report |
| `u_intern` | Iris Lopez | Intern | `read` on public paper only |

### Lineage

```
public_target_paper ──┐
internal_sar_table  ──┼──► phase2_readiness_memo ──► (exec brief — derived in demo)
toxicity_report     ──┤
adverse_event_memo  ──┘
```

Revoking `adverse_event_memo` quarantines `phase2_readiness_memo` and every artifact derived from it.

---

## Request flow

```
Agent runtime (any model)
│
│  POST /query  { "artifact_id": "phase2_readiness_memo", "purpose": "agent_retrieval" }
│  Authorization: Bearer <capability_token>
│
▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI  (:8000)                                                        │
│                                                                          │
│  1. resolve_principal()                                                  │
│     └─ hash bearer token (SHA-256)                                       │
│     └─ look up principal_id in users.token_hash                          │
│     └─ HTTP 401 if not found — no fallback, no ?user_id= override        │
│                                                                          │
│  2. evaluate_access(principal_id, artifact_id, "read")                   │
│     ├─ artifact exists?                            → no  → deny          │
│     ├─ artifact.status in (active, redacted)?      → no  → deny          │
│     ├─ has_grant(principal, artifact, "read")?     → no  → deny          │
│     └─ artifact.type == "derived"?                                       │
│         ├─ for each included transitive parent/source in lineage_edges:   │
│         │   ├─ parent.status in (revoked, quarantined)? → deny           │
│         │   └─ has_grant(principal, parent, "read")?    → no → deny      │
│         └─ redacted-out parents are excluded only by attestation         │
│                                                                          │
│  3. log_audit()                                                          │
│     └─ timestamp, principal_id, artifact_id, operation                   │
│     └─ decision (allow / deny), reason, latency_ms                       │
│     └─ request_id (UUID), structured detail JSON                         │
│                                                                          │
│  4. If decision == allow:                                                │
│     └─ Fernet.decrypt(artifact.encrypted_content)                        │
│     └─ return { decision, plaintext_content, title, sensitivity, … }     │
│                                                                          │
│  5. If decision == deny:                                                 │
│     └─ return { decision, reason, request_id }  — no content             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
│
▼
Agent receives response.
If allow → pass plaintext_content as context to the model.
If deny  → do NOT call the model with this artifact; surface denial to user.
│
▼
Open-weight model generates output using only authorised context.
```

---

## Database schema

```
users
  id            TEXT  PRIMARY KEY
  name          TEXT
  role          TEXT
  team          TEXT
  token_hash    TEXT  UNIQUE    ← SHA-256 of bearer token; plaintext never stored

artifacts
  id            TEXT  PRIMARY KEY
  title         TEXT
  type          TEXT  (source | derived)
  sensitivity   TEXT  (public | internal | restricted | confidential)
  status        TEXT  (active | revoked | quarantined | redacted)
  encrypted_content BLOB
  created_by    TEXT  REFERENCES users(id)
  created_at    TEXT

capability_grants
  id            TEXT  PRIMARY KEY
  user_id       TEXT  REFERENCES users(id)
  artifact_id   TEXT  REFERENCES artifacts(id)
  operation     TEXT  CHECK (operation IN ('read','derive','revoke','grant','redact'))
  revoked       INT   DEFAULT 0
  expires_at    TEXT  NULLABLE

lineage_edges
  parent_artifact_id  TEXT  REFERENCES artifacts(id)
  child_artifact_id   TEXT  REFERENCES artifacts(id)
  dependency_type     TEXT
  inclusion           TEXT  (included | redacted)
  source_hash         TEXT  ← SHA-256 of parent content at derivation time
  created_by          TEXT  REFERENCES users(id)
  reason              TEXT

audit_events
  id            TEXT  PRIMARY KEY
  timestamp     TEXT
  user_id       TEXT
  artifact_id   TEXT
  operation     TEXT
  decision      TEXT  (allow | deny)
  reason        TEXT
  latency_ms    REAL
  request_id    TEXT
  detail        TEXT  (JSON blob)

redaction_attestations
  artifact_id   TEXT  PRIMARY KEY  REFERENCES artifacts(id)
  created_by    TEXT
  created_at    TEXT
  reason        TEXT
  detail        TEXT  (JSON blob — source_hashes, included, redacted parents)
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_grants_lookup
  ON capability_grants (user_id, artifact_id, operation);

CREATE INDEX IF NOT EXISTS idx_lineage_parent
  ON lineage_edges (parent_artifact_id);

CREATE INDEX IF NOT EXISTS idx_lineage_child
  ON lineage_edges (child_artifact_id);

CREATE INDEX IF NOT EXISTS idx_audit_ts
  ON audit_events (timestamp);

CREATE INDEX IF NOT EXISTS idx_users_token
  ON users (token_hash);
```

---

## Security boundary diagram

```
 ┌─────────────────────────────────────────────────────────────┐
 │  OUTSIDE the enforcement boundary                           │
 │                                                             │
 │   ┌─────────────────────────────────────────────────────┐   │
 │   │  Agent / model runtime                              │   │
 │   │  (any open-weight model: Qwen, Llama, Mistral, …)  │   │
 │   │                                                     │   │
 │   │  Calls POST /query to retrieve authorised context.  │   │
 │   │  Generates a response from that context only.       │   │
 │   │  Cannot access any artifact that was denied.        │   │
 │   │  Does NOT influence the permission decision.        │   │
 │   └───────────────────┬─────────────────────────────────┘   │
 │                       │ POST /query                         │
 └───────────────────────┼─────────────────────────────────────┘
                         │
 ┌───────────────────────▼─────────────────────────────────────┐
 │  INSIDE the enforcement boundary                            │
 │                                                             │
 │   resolve_principal → evaluate_access → log_audit           │
 │                                                             │
 │   Deterministic. No model call. No probabilistic path.      │
 │   0 model tokens consumed. Sub-millisecond. Audited.        │
 └─────────────────────────────────────────────────────────────┘
```

---

## Key design decisions

| Decision | Rationale |
|---|---|
| Capability per `(principal, artifact, operation)` | Minimise blast radius — no wildcard grants |
| SHA-256 token hash only stored | Eliminates token leakage via DB read |
| Source-lineage access on every read | Requires the derived artifact grant plus read grants on every included transitive source |
| BFS quarantine on revoke | O(n) where n is number of descendants; consistent regardless of depth |
| Single biotech seed via `POST /seed` | BVK-14 demo graph for AI science agent memory governance |
| SQLite for demo | Zero-infrastructure; replace with PostgreSQL for production concurrency |
| No model in permission path | Permission decisions must be auditable, reproducible, and deterministic |
| `POST /query` as model gate | Single choke point; all agent access goes through the same enforcement stack |
| Governed redaction | Prevents redaction from being used as a bypass around parent capability checks |

The prototype enforces this semantic rule directly at read time. A compiled/effective strictest policy cache is a later optimization for scale, not a different permission model. Redacted/declassified exceptions require explicit authority, source hashes, attestation, and audit; this prototype implements the governed redaction variant.

---

## Open-weight model integration

Any model that supports tool calling or a REST fetch in its agentic loop can integrate with BioVault:

```python
import httpx

def retrieve_artifact(artifact_id: str, capability_token: str) -> dict:
    """Call the BioVault gate before passing content to the model."""
    r = httpx.post(
        "http://localhost:8000/query",
        json={"artifact_id": artifact_id, "purpose": "agent_retrieval"},
        headers={"Authorization": f"Bearer {capability_token}"},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()

# Biotech example — CRO agent attempts Phase II memo:
result = retrieve_artifact("phase2_readiness_memo", cro_token)
if result["decision"] == "allow":
    context = result["plaintext_content"]
    # pass context to model.generate(...)
else:
    print(f"Access denied: {result['reason']} ({result['request_id']})")
    # reason: "missing_capability_grant" (or "derived_from_revoked_source" after adverse-event revocation)
```

The capability token is issued at seed time (`POST /seed`) or via a grant (`POST /artifacts/{id}/grant`) and is passed to the agent by the platform layer. The model itself never holds or manages tokens.

---

## BasedAI judge evidence (honest scope)

| Evidence area | What BioVault proves | What it does not claim |
|---|---|---|
| Retrieval-layer enforcement | `evaluate_access()` runs on every read and `/query` | Production-grade IAM integration |
| Source ACL / revocation sync | Simulated revoke quarantines descendants; stale token denied | Real external ACL event sync |
| No LLM in permission path | Zero model imports/calls in permission decision path | Wired open-weight generation in-repo |
| Audit | `request_id` + structured detail on allow/deny | Tamper-evident compliance-grade audit |
| P99 latency | Local benchmark under 200 ms in tests | Production load test |
| Temporal access (bonus) | `expires_at` checked in `has_grant()` | Full policy calendar engine |
| Query-time gate (bonus) | `/query` deny returns no plaintext | Full semantic inference prevention |
