# BioVault Demo Script

> Audience: Hackathon judges · **BasedAI Enterprise Memory Governance at Scale**

**BioVault is lineage-secured artifact memory for AI science agents.** The demo is the BVK-14 kinase programme: derived Phase II memos, external CRO denial, adverse-event revocation with lineage quarantine.

> **Enforcement boundary:** `GET /artifacts/{id}` and `POST /query` are the retrieval layer — permission is decided here with **no LLM/model call**. Optional open-weight generation runs only after an allow.

---

## Setup (30 seconds)

1. Backend: `uvicorn app.main:app --reload` (port 8000)
2. Frontend: `npm run dev` (port 5173)
3. Open `http://localhost:5173` — biotech demo auto-seeds on load
4. If empty, click **↺ Start / Reset Demo**
5. Point to **Flow Banner**: `Bearer token → resolve_principal() → evaluate_access() → log_audit() → Decrypt (allow only)` — no LLM in this chain

---

## The problem (15 sec)

> "An AI science agent synthesises a Phase II Readiness Memo from toxicity data, SAR tables, and an adverse-event memo. An external CRO must not access that derived memo. When the adverse-event source is revoked for data integrity, every derived clinical artifact that included it must quarantine — automatically, auditable, without routing access decisions through an LLM."

### Why NOT the alternatives?

Point to **Comparison Cards**:

- **Silo copies:** Duplicate lab, CRO, regulatory, and clinical files into separate folders — revoke the canonical source, stale copies persist
- **LLM filtering:** Token-heavy sensitivity filtering over clinical/scientific content — extra model calls, non-deterministic, not a security boundary
- **BioVault:** One shared scientific memory, capability per artifact, lineage propagation, **0 model tokens in permission path**

---

## 90-second demo script (8 steps)

### [0:00–0:10] Intro

> "BioVault is deterministic governed memory for AI science agents. It decides what context a model may see before generation: 0 model tokens in the permission path, every decision audited."

### [0:10–0:20] Step 1 — Regulatory Lead opens Phase II Readiness Memo (ALLOW)

Click **Step 1**.

> "Nora Singh, Regulatory Lead. Capability token resolved. Read grant on `phase2_readiness_memo`. ALLOW — content decrypted."

Point to the **Latest Decision** card: decision, reason, principal, artifact, request_id, latency, plaintext returned.

### [0:20–0:32] Step 2 — External CRO attempts same memo (DENY)

Click **Step 2**.

> "Owen Brooks, External CRO. Same artifact. No capability grant. DENY — `missing_capability_grant`. No clinical content returned."

Red `deny` banner. Empty content panel.

> **Key point:** Deterministic check on artifact ID — not LLM sensitivity filtering.

### [0:32–0:43] Step 3 — Inspect lineage

Click **Step 3**.

> "Four parents feed the derived memo: public target paper, internal SAR table, toxicity report, and adverse-event memo. The read requires the Phase II memo grant plus read grants on every included source in that lineage."

Point to **Lineage** panel.

### [0:43–0:58] Step 4 — Revoke Adverse Event Memo

Click **Step 4**.

> "Data integrity issue on the adverse-event source. CEO revokes it. Watch quarantine cascade to derived artifacts — including the Phase II memo and any child derivations in the demo."

Amber `quarantined` badges. Status message with quarantined IDs.

### [0:58–1:08] Step 5 — Phase II memo quarantined

Click **Step 5**.

> "Phase II readiness memo and descendants now show quarantined status. Revoked adverse_event_memo sealed the derived lineage chain."

### [1:08–1:20] Step 6 — CEO denied on Phase II memo

Click **Step 6**.

> "CEO — who was allowed earlier — is now DENY. `derived_from_revoked_source`. Lineage sealed the derived memo when the source was revoked. No plaintext returned."

### [1:20–1:28] Step 7 — Audit log

Click **Step 7**. Scroll to **Audit Log**. Expand a row.

> "Every decision logged: `request_id`, principal, artifact, operation, decision, reason, purpose, latency_ms. Click any row for structured provenance."

### [1:28–1:30] Step 8 — Permission path evidence

Click **Step 8**. Point to the Flow Banner, token boundary tiles, and **Evidence for judges** if the judge asks for tests.

> "Pure SQL permission check — 0 model tokens, no LLM permission decision. Source-lineage grants are enforced directly today; a compiled effective policy cache would only be a future optimization. Optional open-weight model only runs after authorization via POST /query."

**If asked about BasedAI bonus criteria:**

- **Temporal access:** `expires_at` on capability grants — tested in `test_expired_grant_denies_artifact_read`
- **Query-time gate:** CRO `/query` deny returns no plaintext — tested in `test_cro_query_denied_returns_no_plaintext` (deterministic gate, not full semantic inference prevention)
- **Source ACL sync:** simulated adverse-event revoke quarantines derived memo; stale token denied — `test_stale_capability_denied_after_source_revoke` (not real external IAM)

Optional CLI: `python scripts/demo_agent_cro.py` — External CRO agent attempts Phase II memo via `/query`, prints DENY.

---

## 30-second fallback

> "BioVault secures AI science memory in three ways: **One** — access is per artifact and token, not job title — CRO denied, Regulatory allowed. **Two** — lineage: revoke adverse-event data, Phase II memo quarantines automatically. **Three** — zero model tokens in the permission path — pure SQL, auditable, any agent calls POST /query before generation."

---

## Common judge questions

**Q: How is this different from document ACLs?**  
A: ACLs are flat. BioVault checks lineage dynamically — revoke a source, all derived descendants quarantine via BFS.

**Q: LLM sensitivity filtering?**  
A: That puts a model in the security path — token-heavy, jailbreakable. BioVault's permission path is SQL only.

**Q: Bypass token check?**  
A: No `?user_id=` override. `resolve_principal()` on every protected route. Test: `test_user_id_query_param_is_not_authority`.

**Q: Open-weight model integration?**  
A: `POST /query` is the agent gate — call before generation. No model imported in backend today; integration is the hook, not yet wired in this MVP.

**Q: Performance?**  
A: Indexed lineage traversal. P99 under 200ms in local hackathon tests (`test_permission_latency_p99_under_200ms`) — not a production load test.

**Q: Source ACL / revocation sync?**  
A: Simulated in this prototype — revoke adverse-event memo quarantines derived memos; previously valid tokens are denied (`test_stale_capability_denied_after_source_revoke`). Not real external IAM sync.

**Q: Temporal access or query-time gate?**  
A: Bonus evidence — `expires_at` grant expiry (`test_expired_grant_denies_artifact_read`); CRO `/query` deny with no plaintext (`test_cro_query_denied_returns_no_plaintext`). Deterministic gate only — not full semantic inference prevention.

**Q: Audit compliance-grade?**  
A: Regulatory-style traceability (`request_id`, structured detail) — not tamper-evident compliance-grade audit.

**Q: Does it generalise to other domains?**  
A: The engine is domain-agnostic — capabilities, lineage, revocation, audit. BioVault's product focus is AI science / biotech R&D memory.
