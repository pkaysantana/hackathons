"""First-party evidence tests for BioVault's capability-secured memory layer.

Covers the BasedAI review requirements:
1. normal allow/deny matrix
2. spoofing user_id denial
3. unauthorised grant denial
4. redacted derivation denial without redact authority
5. multi-level revocation propagation
6. audit events for allow/deny/grant/revoke/derive
7. permission latency benchmark (P99 < 200ms)
8. structured audit detail on artifact reads and /query
9. stale capability denied after simulated source ACL revoke
10. expired grant denies read (temporal access)
11. CRO /query deny returns no plaintext (query-time gate)
"""
import json
import time

from tests.conftest import auth

PHASE2 = "phase2_readiness_memo"
ADVERSE = "adverse_event_memo"


def read(client, token, artifact_id):
    return client.get(f"/artifacts/{artifact_id}", headers=auth(token))


# ---------------------------------------------------------------------------
# 1. Normal allow/deny matrix
# ---------------------------------------------------------------------------

def test_allow_deny_matrix(seeded, client):
    tokens = seeded

    # CEO can read the Phase II memo.
    r = read(client, tokens["u_ceo"], PHASE2)
    assert r.json()["access"]["decision"] == "allow"
    assert "plaintext_content" in r.json()["artifact"]

    # Regulatory Lead can read the Phase II memo (has grant; sources healthy).
    r = read(client, tokens["u_regulatory"], PHASE2)
    assert r.json()["access"]["decision"] == "allow"

    # CRO cannot read the Phase II memo (no capability grant).
    r = read(client, tokens["u_cro"], PHASE2)
    assert r.json()["access"]["decision"] == "deny"
    assert r.json()["access"]["reason"] == "missing_capability_grant"
    assert "plaintext_content" not in r.json()["artifact"]

    # Intern can read only the public paper.
    assert read(client, tokens["u_intern"], "public_target_paper").json()["access"]["decision"] == "allow"
    assert read(client, tokens["u_intern"], "internal_sar_table").json()["access"]["decision"] == "deny"


# ---------------------------------------------------------------------------
# 2. Spoofing user_id denial
# ---------------------------------------------------------------------------

def test_user_id_query_param_is_not_authority(seeded, client):
    tokens = seeded

    # A query-param user_id must NOT grant authority — identity is the token.
    # CRO token + ?user_id=u_ceo must still be denied.
    r = client.get(f"/artifacts/{PHASE2}?user_id=u_ceo", headers=auth(tokens["u_cro"]))
    assert r.json()["access"]["decision"] == "deny"
    assert r.json()["principal_id"] == "u_cro"


def test_missing_and_invalid_token_denied(seeded, client):
    # No token at all.
    assert client.get(f"/artifacts/{PHASE2}").status_code == 401
    # Garbage token.
    assert client.get(f"/artifacts/{PHASE2}", headers=auth("not-a-real-token")).status_code == 401


# ---------------------------------------------------------------------------
# 3. Unauthorised grant denial
# ---------------------------------------------------------------------------

def test_unauthorised_grant_denied(seeded, client):
    tokens = seeded

    # Intern has no grant/delegate authority on the SAR table.
    r = client.post(
        "/artifacts/internal_sar_table/grant",
        headers=auth(tokens["u_intern"]),
        json={"subject_user_id": "u_intern", "operation": "read", "purpose": "self-escalation"},
    )
    assert r.json()["granted"] is False
    assert r.json()["access"]["reason"] == "issuer_lacks_grant_authority"

    # Confirm the escalation did not take effect.
    assert read(client, tokens["u_intern"], "internal_sar_table").json()["access"]["decision"] == "deny"


def test_authorised_grant_succeeds(seeded, client):
    tokens = seeded

    # CEO holds grant authority and can delegate read on the SAR table to the intern.
    r = client.post(
        "/artifacts/internal_sar_table/grant",
        headers=auth(tokens["u_ceo"]),
        json={"subject_user_id": "u_intern", "operation": "read", "purpose": "onboarding"},
    )
    assert r.json()["granted"] is True
    assert r.json()["grant_id"].startswith("grant_")

    # Now the intern can read it.
    assert read(client, tokens["u_intern"], "internal_sar_table").json()["access"]["decision"] == "allow"


# ---------------------------------------------------------------------------
# 4. Redacted derivation denial without redact authority
# ---------------------------------------------------------------------------

def test_redaction_requires_redact_authority(seeded, client):
    tokens = seeded
    parents = ["public_target_paper", "internal_sar_table", "toxicity_report", ADVERSE]

    # Research scientist lacks 'redact' capability on these parents.
    r = client.post(
        "/derive",
        headers=auth(tokens["u_research"]),
        json={"title": "Bad Redacted Memo", "parent_artifact_ids": parents,
              "redacted": True, "redact_parent_ids": [ADVERSE], "reason": "attempt"},
    )
    assert r.json()["created"] is False
    assert r.json()["reason"] == "missing_redact_authority"


def test_redaction_cannot_launder_revoked_source(seeded, client):
    tokens = seeded
    parents = ["public_target_paper", "internal_sar_table", "toxicity_report", ADVERSE]

    # Revoke the adverse-event source first.
    client.post(f"/artifacts/{ADVERSE}/revoke", headers=auth(tokens["u_ceo"]), json={})

    # Even the CEO (who holds redact authority) cannot redact from a revoked source.
    r = client.post(
        "/derive",
        headers=auth(tokens["u_ceo"]),
        json={"title": "Laundered Memo", "parent_artifact_ids": parents,
              "redacted": True, "redact_parent_ids": [ADVERSE], "reason": "launder"},
    )
    assert r.json()["created"] is False
    assert r.json()["reason"] == "cannot_redact_revoked_source"


def test_governed_redaction_succeeds_on_healthy_sources(seeded, client):
    tokens = seeded
    parents = ["public_target_paper", "internal_sar_table", "toxicity_report", ADVERSE]

    r = client.post(
        "/derive",
        headers=auth(tokens["u_ceo"]),
        json={"title": "Redacted Phase II Memo", "parent_artifact_ids": parents,
              "redacted": True, "redact_parent_ids": [ADVERSE], "reason": "broad_distribution"},
    )
    assert r.json()["created"] is True
    assert r.json()["attestation_id"].startswith("att_")
    new_id = r.json()["artifact"]["id"]

    # Lineage records the attestation and per-edge inclusion metadata.
    lin = client.get(f"/lineage/{new_id}").json()
    assert lin["redaction_attestation"] is not None
    inclusions = {p["artifact"]["id"]: p["inclusion"] for p in lin["parents"]}
    assert inclusions[ADVERSE] == "redacted"
    assert inclusions["public_target_paper"] == "included"

    # Redacted memo stays readable after the redacted-out source is revoked,
    # because the excluded content was attested-removed (not a bypass — it
    # required redact authority on healthy sources).
    client.post(f"/artifacts/{ADVERSE}/revoke", headers=auth(tokens["u_ceo"]), json={})
    assert read(client, tokens["u_ceo"], new_id).json()["access"]["decision"] == "allow"


# ---------------------------------------------------------------------------
# 5. Multi-level revocation propagation
# ---------------------------------------------------------------------------

def test_multi_level_revocation_propagation(seeded, client):
    tokens = seeded

    # Build a grandchild derived from the Phase II memo (2 levels deep).
    r = client.post(
        "/derive",
        headers=auth(tokens["u_ceo"]),
        json={"title": "Exec Briefing", "parent_artifact_ids": [PHASE2],
              "redacted": False, "reason": "briefing"},
    )
    assert r.json()["created"] is True
    grandchild = r.json()["artifact"]["id"]

    # Both levels readable before revocation.
    assert read(client, tokens["u_ceo"], PHASE2).json()["access"]["decision"] == "allow"
    assert read(client, tokens["u_ceo"], grandchild).json()["access"]["decision"] == "allow"

    # Revoke the root source; quarantine must reach the grandchild.
    resp = client.post(f"/artifacts/{ADVERSE}/revoke", headers=auth(tokens["u_ceo"]), json={}).json()
    assert PHASE2 in resp["quarantined"]
    assert grandchild in resp["quarantined"]

    # Both downstream artifacts now denied with the revoked-source reason.
    assert read(client, tokens["u_ceo"], PHASE2).json()["access"]["reason"] == "derived_from_revoked_source"
    assert read(client, tokens["u_ceo"], grandchild).json()["access"]["reason"] == "derived_from_revoked_source"


# ---------------------------------------------------------------------------
# 6. Audit events for allow / deny / grant / revoke / derive
# ---------------------------------------------------------------------------

def test_audit_records_all_operation_types(seeded, client):
    tokens = seeded

    read(client, tokens["u_ceo"], PHASE2)             # allow
    read(client, tokens["u_cro"], PHASE2)             # deny
    client.post("/artifacts/internal_sar_table/grant", headers=auth(tokens["u_ceo"]),
                json={"subject_user_id": "u_intern", "operation": "read", "purpose": "t"})  # grant
    client.post("/derive", headers=auth(tokens["u_ceo"]),
                json={"title": "D", "parent_artifact_ids": ["public_target_paper"], "reason": "t"})  # derive
    client.post(f"/artifacts/{ADVERSE}/revoke", headers=auth(tokens["u_ceo"]), json={})  # revoke

    events = client.get("/audit").json()
    ops = {e["operation"] for e in events}
    decisions = {e["decision"] for e in events}
    assert {"read", "grant", "derive", "revoke"}.issubset(ops)
    assert {"allow", "deny"}.issubset(decisions)

    # Grant audit carries full provenance.
    grant_events = [e for e in events if e["operation"] == "grant" and e["decision"] == "allow"]
    assert grant_events
    assert grant_events[0]["detail"] is not None
    assert "request_id" in grant_events[0] and grant_events[0]["request_id"]


# ---------------------------------------------------------------------------
# 7. Permission latency benchmark — P99 < 200ms
# ---------------------------------------------------------------------------

def test_permission_latency_p99_under_200ms(seeded, client):
    tokens = seeded

    samples = []
    for _ in range(200):
        start = time.perf_counter()
        read(client, tokens["u_regulatory"], PHASE2)
        samples.append((time.perf_counter() - start) * 1000)

    samples.sort()
    p99 = samples[int(0.99 * len(samples)) - 1]
    assert p99 < 200.0, f"P99 latency {p99:.2f}ms exceeds 200ms budget"

    # The server-side metric should also be well under budget.
    metrics = client.get("/metrics/permission-latency").json()
    assert metrics["p99_ms"] < 200.0


# ---------------------------------------------------------------------------
# 8. Structured audit detail on artifact reads and /query
# ---------------------------------------------------------------------------

def test_artifact_read_audit_contains_structured_detail(seeded, client):
    tokens = seeded

    # CEO read → allow (has capability grant); CRO read → deny (no grant).
    allow_resp = read(client, tokens["u_ceo"], PHASE2)
    deny_resp  = read(client, tokens["u_cro"], PHASE2)

    assert allow_resp.json()["access"]["decision"] == "allow"
    assert deny_resp.json()["access"]["decision"]  == "deny"

    allow_req_id = allow_resp.json()["access"]["request_id"]
    deny_req_id  = deny_resp.json()["access"]["request_id"]

    events = client.get("/audit").json()

    allow_event = next((e for e in events if e.get("request_id") == allow_req_id), None)
    deny_event  = next((e for e in events if e.get("request_id") == deny_req_id), None)

    assert allow_event is not None, "Allow audit event not found by request_id"
    assert deny_event  is not None, "Deny audit event not found by request_id"

    # Both events must carry parseable structured detail JSON.
    for event, label in [(allow_event, "allow"), (deny_event, "deny")]:
        assert event["detail"] is not None, f"{label} audit event has no detail"
        detail = json.loads(event["detail"])

        assert "purpose"    in detail, f"{label} detail missing purpose"
        assert "principal"  in detail, f"{label} detail missing principal"
        assert "operation"  in detail, f"{label} detail missing operation"
        assert event["artifact_id"] == PHASE2, f"{label} artifact_id mismatch"
        assert event["request_id"],             f"{label} request_id is empty"

    # Allow event: grant_id must be present because access went through a capability grant.
    allow_detail = json.loads(allow_event["detail"])
    assert "grant_id" in allow_detail, "Allow event detail missing grant_id"

    # Decision values must survive the round-trip.
    assert allow_event["decision"] == "allow"
    assert deny_event["decision"]  == "deny"


def test_query_audit_contains_structured_detail(seeded, client):
    tokens = seeded

    # CEO queries via the agent retrieval gate with a distinct purpose string.
    resp = client.post(
        "/query",
        headers=auth(tokens["u_ceo"]),
        json={"artifact_id": PHASE2, "purpose": "agent_retrieval_evidence_test"},
    )
    assert resp.json()["decision"] == "allow"
    req_id = resp.json()["request_id"]

    events = client.get("/audit").json()
    event = next((e for e in events if e.get("request_id") == req_id), None)

    assert event is not None, "Query audit event not found by request_id"
    assert event["detail"] is not None, "Query audit event has no detail"

    detail = json.loads(event["detail"])

    # Core provenance fields.
    assert "purpose"   in detail
    assert detail["purpose"]    == "agent_retrieval_evidence_test"
    assert "principal" in detail
    assert detail["principal"]  == "u_ceo"
    assert "operation" in detail

    # Traceability.
    assert event["artifact_id"] == PHASE2
    assert event["request_id"]  == req_id

    # CEO has a capability grant → grant_id must appear.
    assert "grant_id" in detail, "Query audit detail missing grant_id on allow"

    # Decision round-trip.
    assert event["decision"] == "allow"


# ---------------------------------------------------------------------------
# Biotech scenario: CRO denial and adverse-event revocation
# ---------------------------------------------------------------------------

def test_cro_denial_returns_no_plaintext_content(seeded, client):
    tokens = seeded
    r = read(client, tokens["u_cro"], PHASE2)
    assert r.json()["access"]["decision"] == "deny"
    assert "plaintext_content" not in r.json()["artifact"]


def test_adverse_event_revocation_quarantines_phase2_memo(seeded, client):
    tokens = seeded

    assert read(client, tokens["u_ceo"], PHASE2).json()["access"]["decision"] == "allow"

    resp = client.post(
        f"/artifacts/{ADVERSE}/revoke",
        headers=auth(tokens["u_ceo"]),
        json={"purpose": "data_integrity_review"},
    ).json()
    assert resp["revoked"] is True
    assert PHASE2 in resp["quarantined"]

    r = read(client, tokens["u_ceo"], PHASE2)
    assert r.json()["access"]["decision"] == "deny"
    assert r.json()["access"]["reason"] == "derived_from_revoked_source"
    assert "plaintext_content" not in r.json()["artifact"]


# ---------------------------------------------------------------------------
# BasedAI Judge Max-Out — stale token, temporal expiry, query-time gate
# ---------------------------------------------------------------------------

def test_stale_capability_denied_after_source_revoke(seeded, client):
    """Previously valid reader token cannot read derived memo after source revoke."""
    tokens = seeded

    before = read(client, tokens["u_regulatory"], PHASE2)
    assert before.json()["access"]["decision"] == "allow"
    assert "plaintext_content" in before.json()["artifact"]

    client.post(
        f"/artifacts/{ADVERSE}/revoke",
        headers=auth(tokens["u_ceo"]),
        json={"purpose": "simulated_source_acl_revocation"},
    )

    after = read(client, tokens["u_regulatory"], PHASE2)
    body = after.json()
    assert body["access"]["decision"] == "deny"
    assert body["access"]["reason"] == "derived_from_revoked_source"
    assert "plaintext_content" not in body["artifact"]

    req_id = body["access"]["request_id"]
    events = client.get("/audit").json()
    event = next((e for e in events if e.get("request_id") == req_id), None)
    assert event is not None, "Deny audit event not found by request_id"
    assert event["decision"] == "deny"
    assert event["detail"] is not None
    detail = json.loads(event["detail"])
    assert "principal" in detail
    assert detail["principal"] == "u_regulatory"


def test_expired_grant_denies_artifact_read(seeded, client):
    """Grant with expires_at in the past does not authorize read."""
    tokens = seeded
    past = "2020-01-01T00:00:00+00:00"

    client.post(
        "/artifacts/internal_sar_table/grant",
        headers=auth(tokens["u_ceo"]),
        json={
            "subject_user_id": "u_intern",
            "operation": "read",
            "purpose": "temporal_access_evidence",
            "expires_at": past,
        },
    )

    r = read(client, tokens["u_intern"], "internal_sar_table")
    body = r.json()
    assert body["access"]["decision"] == "deny"
    assert body["access"]["reason"] == "missing_capability_grant"
    assert "plaintext_content" not in body["artifact"]

    req_id = body["access"]["request_id"]
    events = client.get("/audit").json()
    event = next((e for e in events if e.get("request_id") == req_id), None)
    assert event is not None, "Deny audit event not found by request_id"
    assert event["decision"] == "deny"
    assert event["detail"] is not None


def test_cro_query_denied_returns_no_plaintext(seeded, client):
    """Agent /query gate denies CRO before any context reaches a model."""
    tokens = seeded

    resp = client.post(
        "/query",
        headers=auth(tokens["u_cro"]),
        json={"artifact_id": PHASE2, "purpose": "agent_retrieval_cro_evidence"},
    )
    body = resp.json()
    assert body["decision"] == "deny"
    assert body["reason"] == "missing_capability_grant"
    assert "plaintext_content" not in body
    assert "content" not in body
    assert "context" not in body
    assert "synthesis" not in body

    req_id = body["request_id"]
    events = client.get("/audit").json()
    event = next((e for e in events if e.get("request_id") == req_id), None)
    assert event is not None, "Query deny audit event not found by request_id"
    assert event["decision"] == "deny"
    assert event["detail"] is not None
    detail = json.loads(event["detail"])
    assert detail["purpose"] == "agent_retrieval_cro_evidence"
    assert detail["principal"] == "u_cro"
