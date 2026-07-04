# BioVault Submission Hygiene Checklist

Use this checklist before final upload or demo rehearsal.

## Required Evidence

- [ ] `README.md` explains BioVault as lineage-secured memory for AI science agents.
- [ ] `docs/PRD.md` states goals, non-goals, and prototype scope.
- [ ] `docs/REQUIREMENTS_TRACEABILITY.md` maps claims to implementation and tests.
- [ ] `docs/EVALUATION_HARNESS.md` gives exact judge verification commands.
- [ ] `docs/adr/0001-derived-artifact-policy-semantics.md` records the derived artifact policy decision.
- [ ] `docs/THREAT_MODEL.md` states trust boundaries, assumptions, residual risks, and non-claims.
- [ ] `scripts/verify_submission.py` passes.

## Product Logic Freeze

- [ ] No changes to `backend/app/main.py`.
- [ ] No auth, grant, redaction, lineage, revocation, database, or `/query` logic changes.
- [ ] No dependency changes.
- [ ] No deployment file changes unless only documenting a known deployed URL.
- [ ] No new model or LLM call.
- [ ] No live payment, chain, remittance, or settlement behavior.

## Verification

```powershell
python scripts/verify_submission.py
cd backend
python -m pytest -q
cd ..\frontend
npm run build
```

## Claim Hygiene

- [ ] Do not claim production security.
- [ ] Do not claim clinical decision support.
- [ ] Do not claim real external ACL sync.
- [ ] Do not claim full Hirebase integration.
- [ ] Do not claim production load testing.
- [ ] Do not claim full semantic inference prevention.
- [ ] Keep the submission biotech and AI-science first.

## Demo Hygiene

- [ ] Demo starts from the BVK-14 seed state.
- [ ] Regulatory Lead allow path works.
- [ ] External CRO deny path returns no plaintext.
- [ ] Lineage panel shows included sources.
- [ ] Adverse Event Memo revoke quarantines derived artifacts.
- [ ] CEO is denied after source revocation.
- [ ] Audit log shows request IDs and structured provenance.

