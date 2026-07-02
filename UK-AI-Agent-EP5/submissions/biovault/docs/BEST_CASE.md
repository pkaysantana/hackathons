# BioVault — Best Case by Demo Day

**Horizon:** now → **4 Jul 2026**  
**Identity:** Lineage-secured memory for AI science agents

BioVault was built for **pharma AI agents**: derived clinical memos, adverse-event sources, external CRO access boundaries, and revocation that propagates through scientific lineage.

---

## One sentence (what you say on stage)

> "BioVault governs what AI science agents can retrieve from shared R&D memory — when we revoke an adverse-event source for data integrity, every derived Phase II memo is quarantined automatically, the external CRO is denied, and every decision is audited with zero LLM calls in the permission path."

---

## Best-case Demo Day (2 minutes) — biotech

What judges **see**:

1. Live URL opens — dashboard loads **BVK-14 kinase programme** demo
2. **Start / Reset Demo** — biotech artifacts appear (Phase II memo, SAR table, adverse-event memo, …)
3. **Nora Singh (Regulatory Lead)** opens **Phase II Readiness Memo** → **ALLOW** — derived from four source documents, content shown
4. **Owen Brooks (External CRO)** attempts same memo → **DENY** — `missing_capability_grant`, no clinical content leaked
5. Lineage view: public_target_paper + internal_sar_table + toxicity_report + adverse_event_memo → phase2_readiness_memo
6. **CEO revokes Adverse Event Memo** (data integrity) → quarantine cascades to derived memos
7. Phase II memo shows **quarantined** — amber badges
8. **CEO** opens Phase II memo again → **DENY** — `derived_from_revoked_source`
9. Audit log: structured `request_id`, principal, purpose, latency_ms on every step
10. Permission path: 0 model tokens, deterministic SQL, optional open-weight model only after authorization
11. **Optional:** science agent script asks "Summarise Phase II readiness for the board" as CRO → `/query` deny → no synthesis from protected clinical data

**Under 2 minutes. Deterministic. On-brand for BioVault.**

---

## What BioVault is (and isn't)

| BioVault **is** | BioVault **is not** |
|---|---|
| Governance gate for **scientific artifact memory** | RBAC with a React skin |
| Lineage-aware revocation for **derived clinical memos** | LLM-based sensitivity filtering |
| Capability tokens for **CEO / CRO / Regulatory** roles | A full autonomous agent (yet) |
| Audit trail for **regulated R&D contexts** | Open-weight model integrated (yet — optional stretch) |
| LLM-free permission path | Production clinical decision support |

---

## Best-case product shape

```
┌──────────────────────────────────────────────────────────────┐
│  React dashboard                                              │
│  · BVK-14 biotech demo (8 steps)                             │
│  · Shared Scientific Memory · lineage · audit · compliance   │
└────────────────────────────┬─────────────────────────────────┘
                             │ POST /query
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  BioVault gate (FastAPI)                                      │
│  · capability per (principal, artifact, operation)           │
│  · lineage integrity on every read                           │
│  · revoke source → BFS quarantine descendants                │
│  · 0 LLM calls in permission path                            │
└────────────────────────────┬─────────────────────────────────┘
                             │ plaintext only if allow
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  AI science agent (OPTIONAL stretch)                          │
│  · e.g. Ollama — only after BioVault allow                   │
│  · CRO agent demo: deny on Phase II memo = no clinical leak  │
└──────────────────────────────────────────────────────────────┘
```

---

## Feature tiers

### Tier 1 — Must ship (credible + on-brand)

| Feature | Status | Demo Day role |
|---|---|---|
| Biotech seed (BVK-14, Phase II memo, adverse event) | ✅ Built | **Primary story** |
| CRO deny / regulatory allow / CEO revoke cascade | ✅ Built | Core proof |
| Lineage + audit | ✅ Built | Regulated R&D trust |
| **Biotech-only identity in docs + UI** | ✅ Done | Coherent identity |
| Live deploy + biotech video | ❌ TODO | Judges can verify |
| PR #3 + honest submission README | ✅ Mostly | First impression |

### Tier 2 — Best case (strong pitch)

| Feature | Status | Why |
|---|---|---|
| **CRO agent script** (`POST /query` deny) | ✅ Built | `scripts/demo_agent_cro.py` — autonomous agent without faking it |
| Rehearsed 2-min biotech script | Stage confidence |
| 3 biotech screenshots in README | Visual proof |

### Tier 3 — Stretch

| Feature | Why |
|---|---|
| "Ask the science agent" UI panel | Shows agent + gate together |
| Ollama summarisation **after** allow | Open-weight compliance with real model |
| Multi-level quarantine visible in UI (exec brief → Phase II) | Already partially in step 4 |

### Not the best case (wrong direction)

- Non-biotech demo narratives (outside Phase II readiness, CRO handoffs, regulatory summaries, or clinical lineage) anywhere user-facing
- Claiming LLM integration that isn't wired up
- Building features unrelated to AI science memory governance

---

## Best-case judge narrative

### Problem (15 sec) — biotech

AI science agents derive Phase II readiness memos from adverse-event reports, SAR tables, and toxicity data. When a source document is revoked for data integrity, **derived memos built from it must not remain accessible** — especially to external CROs. Folder copies and role labels don't track derivation.

### Approach (15 sec)

BioVault: one canonical R&D artifact store, explicit capabilities per principal and artifact, lineage on every derivation, deterministic revoke propagation, full audit. **No LLM decides access.**

### Proof (60 sec)

Live biotech demo — 8 steps above.

### Why BasedAI track (15 sec)

Enterprise memory governance at scale — in AI science, "memory" is derived clinical knowledge. BioVault enforces **who may surface which derived artifact** before any open-weight model sees it.

---

## Best-case README (submission)

Judges read this first. It should open with:

1. **BioVault** — lineage-secured memory for AI science agents
2. Problem: derived clinical artifacts + revocation + external collaborator boundaries
3. Approach: capabilities, lineage, revocation, audit
4. Demo: biotech steps + live URL + video
5. BasedAI requirement mapping
6. Open-weight compliance: model-free permission path
7. How to run + limitations

---

## Best-case minimal agent (biotech)

**`scripts/demo_agent_cro.py`**

```text
1. Load External CRO bearer token (from POST /seed)
2. Question: "Summarise Phase II readiness for the investor deck"
3. Target artifact: phase2_readiness_memo
4. POST /query → deny, missing_capability_grant
5. Print: "BioVault denied access to Phase II Readiness Memo. Cannot generate summary."
6. No clinical content printed — ever
```

This is the agent story **for BioVault**.

---

## Day-by-day best case

| Day | Outcome |
|---|---|
| **30 Jun** | Biotech-only identity restored (UI, README, DEMO_SCRIPT, tests) |
| **1 Jul** | Live deploy; biotech video; CRO agent script |
| **2 Jul** | Three biotech rehearsals; screenshots; submission sync |
| **3 Jul** | PR frozen; submission README is biotech-first |
| **4 Jul** | Stage demo: BVK-14 → CRO deny → revoke → quarantine → audit |

---

## What success looks like

**Minimum:** Biotech-first docs + live biotech demo + video + PR → submission that matches what you built.

**Best case:** Judges remember *"clinical lineage quarantine when adverse events are revoked"* and *"zero model tokens in the permission path."*

**Failure mode to avoid:** Judges think the product identity is unclear or off-brand for AI science.

---

## After Demo Day (vision — biotech-centred)

- FHIR / ELN connectors for real R&D systems
- Policy: "CRO may never read artifacts with adverse-event lineage"
- Integration with open-weight science agents (literature review, trial design)
- PostgreSQL + KMS for production pharma IT

---

*Action list: [TODO.md](TODO.md)*
