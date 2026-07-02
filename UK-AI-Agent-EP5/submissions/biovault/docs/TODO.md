# BioVault — Pre–Demo Day TODO

**Today → submission deadline:** 3 Jul 2026 (end of day)  
**Demo Day:** 4 Jul 2026  
**Official PR:** [BasedAICo/hackathons#3](https://github.com/BasedAICo/hackathons/pull/3)

---

## What BioVault actually is (don't lose this)

BioVault is **lineage-secured memory for AI science agents** — a capability-secured artifact store for pharma/biotech R&D where AI agents derive clinical memos from source documents, and **revoking a compromised source quarantines every derived artifact downstream**.

That is the project: kinase program BVK-14, Phase II readiness memo, adverse-event revocation, CRO denied.

**Demo Day story = biotech only.**

---

## Identity checklist (quick audit)

Before you ship anything, ask:

| Question | Should be |
|---|---|
| Default seed | Biotech (BVK-14) |
| Hero copy | AI science / lineage-secured memory |
| Demo | Phase II memo → CRO deny → adverse-event revoke |
| CRO denial shown | External CRO denied Phase II memo, no plaintext |
| Revocation shown | adverse_event_memo revoke quarantines Phase II memo |
| Biotech-only narrative | No non-science examples in UI, docs, tests, or seed |
| What track is this? | BasedAI Enterprise Memory Governance — via scientific artifact lineage |

---

## Restore identity

- [x] **Default seed → biotech only** — `POST /seed`; no scenario switcher
- [x] **README** — lineage-secured memory for AI science agents; biotech-only framing
- [x] **DEMO_SCRIPT.md** — biotech 8-step script only
- [x] **ARCHITECTURE.md** — biotech worked example only
- [x] **UI hero copy** — AI science; no scenario switcher
- [x] **Biotech-only tests and seed** — no non-science scenario coverage

---

## Must do (submission breaks without these)

### Hackathon admin

- [ ] Confirm [PR #3](https://github.com/BasedAICo/hackathons/pull/3) is open and only touches `UK-AI-Agent-EP5/submissions/biovault/`
- [ ] Submission `README.md` leads with **biotech identity** + accurate team handle
- [ ] Final push to `submit/biovault` before **3 Jul EOD**
- [ ] Smoke test from clean clone → seed → demo steps 1–8 ([DEMO_SCRIPT.md](DEMO_SCRIPT.md))

### Demo that judges can actually see

- [ ] **Live deploy** — [docs/DEPLOYMENT.md](DEPLOYMENT.md)
- [ ] After deploy: seed biotech, verify CRO deny → revoke adverse event → Phase II memo quarantined
- [ ] Live URL in submission README

### Demo Day presentation

- [ ] **2-minute demo rehearsed** — biotech path:
  1. Regulatory Lead opens Phase II Readiness Memo → **ALLOW**
  2. External CRO attempts same memo → **DENY**
  3. Inspect lineage → four parents → derived memo
  4. CEO revokes Adverse Event Memo → quarantine cascades
  5. Phase II memo shows quarantined
  6. CEO opens Phase II memo again → **DENY** (`derived_from_revoked_source`)
  7. Audit log — request_id, provenance, latency
  8. Permission path — 0 model tokens
- [ ] **Demo video** (≤3 min) — biotech walkthrough
- [ ] Screenshots from biotech flow (CRO deny, quarantine badge, audit row)

---

## High impact (strongly recommended)

### Close the "where's the agent?" gap — biotech framing

- [x] Minimal **agent script** calling `POST /query` as an **AI science agent** (External CRO token) — `scripts/demo_agent_cro.py`
- [x] Script tries to retrieve Phase II Readiness Memo → **denied** → agent refuses to summarise (no clinical leak)
- [ ] Document which open-weight model (if any) — only **after** `/query` allow

| Option | Effort | Notes |
|---|---|---|
| **A. CLI agent** (httpx, CRO token) | ~2 hrs | On-brand, easy to demo |
| **B. "Science agent preview" in UI** | ~4–6 hrs | Shows `/query` in dashboard |
| **C. Ollama + scripted clinical question** | ~1–2 days | Strongest, only if Tier 1 done |

### Pitch materials

- [ ] One-liner memorised: *"When adverse-event data is revoked for integrity, BioVault quarantines every AI-derived clinical memo that included it — deterministically, audited, no LLM in the permission path."*
- [ ] Name consistency across READMEs (Santana / Aborah)

### Tests & stability

- [x] `python -m pytest -q` — 35 tests including Judge Max-Out pack
- [ ] `npm run build` — clean
- [ ] Re-seed on deployed URL after cold start

### Judge Max-Out evidence (BasedAI)

- [x] `test_stale_capability_denied_after_source_revoke` — simulated source ACL/revocation
- [x] `test_expired_grant_denies_artifact_read` — temporal `expires_at` grant check
- [x] `test_cro_query_denied_returns_no_plaintext` — query-time gate, no plaintext on deny
- [x] README requirement mapping table (implementation / evidence / honest scope)
- [x] UI Evidence for judges rows (temporal, query gate, simulated ACL sync)
- [x] `scripts/demo_agent_cro.py` — optional CRO agent CLI

---

## Nice to have

- [ ] Repo About: "BioVault — lineage-aware governance for AI science memory"
- [ ] Architecture diagram centred on **clinical derivation** flow
- [ ] Lineage panel screenshot showing adverse_event_memo → phase2_readiness_memo chain

---

## Already done

- [x] Permission engine (capabilities, lineage, revoke propagation, audit)
- [x] Biotech seed data (BVK-14, Phase II memo, adverse event, CRO/CEO/regulatory principals)
- [x] Biotech 8-step demo flow in UI
- [x] Biotech pytest coverage (CRO deny, adverse-event revocation, Judge Max-Out pack)
- [x] Submission folder + PR #3
- [x] Deploy configs

---

## Suggested schedule

### 30 Jun – 1 Jul — identity + deploy

| Task | Est. |
|---|---|
| Biotech-only restore (code + README + DEMO_SCRIPT) | Done |
| Vercel deploy + biotech smoke test | 1–2 hrs |
| Record **biotech** demo video | 1 hr |
| CRO agent script (option A) | 2 hrs |

### 2 Jul — freeze

| Task | Est. |
|---|---|
| Rehearse biotech demo ×3 on live URL | 1 hr |
| Sync submission folder → push `submit/biovault` | 30 min |
| Biotech screenshots for README | 30 min |

### 3 Jul — submit

| Task | Est. |
|---|---|
| PR #3 final check | 30 min |
| Submission README = biotech-first | 15 min |

### 4 Jul — Demo Day

| Task | |
|---|---|
| Live biotech demo, ≤2 min | |
| Local backup running biotech seed | |

---

## Blockers

| Decision | Pick by |
|---|---|
| Agent demo: CLI vs UI vs Ollama | 1 Jul |
| Live URL vs video-only fallback | 1 Jul |

---

*Last updated: 30 Jun 2026*
