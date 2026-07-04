# BioVault Evaluation Harness

This guide gives judges and reviewers a reproducible way to verify the BioVault submission without changing product logic or calling external model, payment, or chain systems.

## Prerequisites

- Python 3.12+
- Node.js with npm
- The commands are run from `UK-AI-Agent-EP5/submissions/biovault/`

## Static Submission Check

```powershell
python scripts/verify_submission.py
```

The verifier is stdlib-only and read-only. It checks that required evidence docs exist, expected tests are present, past non-biotech demo wording is absent from relevant source/docs, backend permission code does not import common model SDKs, and expected submission links exist.

## Backend Tests

```powershell
cd backend
python -m pytest -q
```

Key behaviors covered:

- target artifact grant and source-lineage grants
- revoked/quarantined source denial
- governed redaction and source hashes
- `/query` denial with no plaintext
- audit structure
- local P99 latency benchmark
- temporal grant expiry

## Frontend Build

```powershell
cd frontend
npm run build
```

This verifies that the judge-facing demo UI compiles. It does not change backend semantics.

## Optional CRO Agent Gate Demo

Start the backend first:

```powershell
cd backend
uvicorn app.main:app --reload
```

Then, from the submission root:

```powershell
python scripts/demo_agent_cro.py
```

Expected result: External CRO receives `DENY` for `phase2_readiness_memo` through `/query`, and the response contains no plaintext/context.

## Manual Demo Path

1. Start backend: `cd backend; uvicorn app.main:app --reload`
2. Start frontend: `cd frontend; npm run dev`
3. Open `http://localhost:5173`
4. Click the guided demo steps in order.
5. Confirm the same request path appears in the Flow Banner: bearer token, principal resolution, access evaluation, audit logging, decrypt on allow only.

## Scope of This Harness

- It does not call an LLM or model provider.
- It does not perform live chain, payment, remittance, or settlement actions.
- It does not validate production security, production-scale performance, clinical decision support, full external ACL sync, or full semantic inference prevention.

