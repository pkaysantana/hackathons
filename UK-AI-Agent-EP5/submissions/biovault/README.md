# BioVault — lineage-secured memory for AI science agents

**Capability-bound artifact memory with deterministic access, lineage propagation, and full audit — no LLM in the permission path.**

Hackathon MVP · **BasedAI Enterprise Memory Governance at Scale**

**Team:** BioVault · [@pkaysantana](https://github.com/pkaysantana) (Don Aborah)  
**Submission:** [BasedAICo/hackathons#3](https://github.com/BasedAICo/hackathons/pull/3) · [pkaysantana/hackathons](https://github.com/pkaysantana/hackathons)

> Educational prototype only — not production security or clinical decision support.

---

## The AI-science problem

AI science agents generate **Phase II readiness memos**, **CRO handoffs**, **regulatory summaries**, and **scientific reports** from sensitive source documents — SAR tables, toxicity reports, adverse-event memos, and public target biology.

When a source is revoked for data integrity, every **derived artifact** that included it must quarantine automatically. External CROs must not read clinical memos they were never granted. Duplicating files into lab, CRO, and regulatory silos creates drift — revoke the canonical source and stale copies persist.

---

## Approach

BioVault is a **permission gate + demo dashboard** for shared scientific artifact memory. It is **not** an AI agent and **does not call any LLM**.

It avoids token-heavy permission prompts by enforcing deterministic governance before generation:
models only receive authorized context after capability, lineage, revocation, and audit checks pass.

| Mechanism | What it does |
|---|---|
| **Capability tokens** | Bearer token → `(principal, artifact, operation)` grant before any read |
| **Deterministic access** | Pure SQL permission check — 0 model tokens, sub-millisecond |
| **Lineage** | Derived reads require the target grant plus read grants on every included source in the transitive lineage |
| **Revocation propagation** | Revoke a source → BFS quarantine of all descendants |
| **Audit** | Every decision logged with `request_id`, principal, operation, reason, latency, structured provenance |

BioVault enforces the source-lineage rule directly in this prototype. A compiled/effective strictest policy cache is a later optimization, not a separate trust path. Redacted/declassified exceptions require explicit authority, source hashes, attestation, and audit; this prototype implements the governed redaction variant.

---

## Demo: BVK-14 kinase programme

Seed with **Start / Reset Demo** or `POST /seed`.

**Story:** An AI science program (kinase BVK-14) derives a **Phase II Readiness Memo** from source documents including an **Adverse Event Memo**. External CRO must not access the derived memo. When the adverse-event source is revoked, the Phase II memo quarantines automatically.

```
public_target_paper ──┐
internal_sar_table  ──┼──► phase2_readiness_memo  (derived, confidential)
toxicity_report     ──┤
adverse_event_memo  ──┘
```

| Step | Principal | Action | Result |
|---|---|---|---|
| 1 | Nora Singh (Regulatory Lead) | Read Phase II Readiness Memo | **ALLOW** |
| 2 | Owen Brooks (External CRO) | Read Phase II Readiness Memo | **DENY** — no capability grant, no plaintext |
| 3 | — | Inspect lineage | Four parents → derived memo |
| 4 | Avery Chen (CEO) | Revoke Adverse Event Memo | Quarantine propagates to derived memos |
| 5 | — | Phase II memo quarantined | Amber badges on derived chain |
| 6 | CEO | Read Phase II memo again | **DENY** — `derived_from_revoked_source` |
| 7 | — | Audit log | `request_id`, principal, provenance, latency |
| 8 | — | Permission path | Deterministic SQL · 0 model tokens |

Full walkthrough: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

---

## BasedAI requirement mapping

| Requirement | BioVault implementation | Evidence | Honest scope |
|---|---|---|---|
| Source ACL sync under concurrent updates | Simulated source ACL/revocation event revokes source and quarantines descendants | `test_stale_capability_denied_after_source_revoke` | Not real external IAM sync yet |
| Deterministic retrieval-layer enforcement | `evaluate_access()` / `can_access()` before artifact read or `POST /query` | `test_allow_deny_matrix`, `backend/app/main.py` | Deterministic SQL/Python path |
| No LLM in permission path | No model imports or calls in backend permission path | Code scan; UI compliance matrix | Optional generation only after authorization |
| Audit logs | `request_id`, principal, artifact, operation, decision, reason, latency_ms, structured detail | `test_artifact_read_audit_contains_structured_detail`, `test_audit_records_all_operation_types` | Regulatory-style traceability — not tamper-evident compliance-grade audit |
| P99 under 200 ms | Permission latency benchmark + live metrics | `test_permission_latency_p99_under_200ms`, `GET /metrics/permission-latency` | Local hackathon benchmark — not production load test |
| Derived memory lineage | Read requires the derived artifact grant plus read grants on every included transitive source; redacted-out sources are explicit governed exceptions | `test_derived_artifact_requires_included_source_grants`, `test_governed_redaction_succeeds_on_healthy_sources`, lineage API | Prototype lineage graph; no compiled policy cache yet |
| Source revocation propagation | BFS quarantine of descendants on revoke | `test_multi_level_revocation_propagation`, `test_adverse_event_revocation_quarantines_phase2_memo` | Simulated source revocation |
| Open-weight compliance | Permission layer is model-free; optional model after authorization can be open-weight | No closed-model runtime dependency; `POST /query` gate | Open-weight compatible — not deeply integrated |
| Bonus: temporal access | `expires_at` grant check in `has_grant()` | `test_expired_grant_denies_artifact_read` | Grant expiry demo — not full policy calendar engine |
| Bonus: query-time inference prevention | `POST /query` denies before context/model; no plaintext on deny | `test_cro_query_denied_returns_no_plaintext` | Deterministic gate — not full semantic inference prevention |

---

## Open-weight model compliance

The **permission path is model-free**. No closed-model dependencies. Optional generation **after** authorization can use open-weight models (Qwen, Llama, Mistral, GLM, BGE, E5, Nomic, etc.) via `POST /query`:

```python
# Agent calls BioVault before passing content to any model
result = httpx.post("/query", json={"artifact_id": "phase2_readiness_memo", ...},
                    headers={"Authorization": f"Bearer {cro_token}"})
if result["decision"] != "allow":
    # Do not call the model — surface denial to user
    ...
```

Nothing in this repo calls a model yet; the hook is the integration point.

---

## How to run

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` — BVK-14 demo loads automatically.

### API (`backend/app/main.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness |
| POST | `/seed` | — | Reset DB; biotech demo; returns bearer tokens once |
| GET | `/artifacts/{id}` | Bearer | Read with permission check + audit |
| POST | `/query` | Bearer | Agent gate — content only if allowed |
| POST | `/artifacts/{id}/revoke` | Bearer | Revoke source + quarantine descendants |
| GET | `/lineage/{id}`, `/audit`, `/metrics/permission-latency` | — | Lineage, audit, latency |

### Tests

```powershell
cd backend
python -m pytest -q
```

Planning: [docs/TODO.md](docs/TODO.md) · [docs/BEST_CASE.md](docs/BEST_CASE.md) · Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

### Optional CRO agent script

```powershell
python scripts/demo_agent_cro.py
```

External CRO science agent calls `POST /query` for `phase2_readiness_memo` → **DENY** — no synthesis from protected clinical data. Set `BIOVAULT_BASE_URL` for a deployed backend.

---

## Limitations

- **Prototype** — educational demo, not production security
- **Local SQLite** — single-process; replace with PostgreSQL for production
- **Simulated revocation/ACL events** — no external IAM or HSM/key management
- **No full Hirebase integration** — capability tokens issued at seed time
- **No LLM wired up** — permission path is complete; agent generation is optional stretch

---

## License

MIT — BioVault team. See [LICENSE](LICENSE).
