"""Tests for SikaRoute Market agent spending policy (Kaspa-ready hook)."""

import json

from app.sika_route import (
    DEMO_SCENARIOS,
    KASPA_POLICY_HASH_LABEL,
    canonical_json,
    evaluate_spending_policy,
    run_demo_scenario,
    run_market_round,
    sha256_hex,
)
from app.sika_route import MarketRoundInput as RoundInput


def _base_round(**overrides) -> RoundInput:
    defaults = {
        "market_id": "mkt_test_001",
        "buyer_agent": "coral-buyer",
        "selected_seller_agent": "sika-seller",
        "corridor": "US-KE",
        "report_value": 50.0,
        "risk_level": "low",
        "request_payload": {"route": "US-KE", "amount": 50.0},
        "bid_payload": {"seller": "sika-seller", "fee_bps": 80},
        "delivery_payload": {"status": "delivered"},
        "disclaimer": "SikaRoute demo — testnet only. No real user funds. No personal data on-chain.",
    }
    defaults.update(overrides)
    return RoundInput(**defaults)


def test_low_risk_low_value_auto_approved():
    result = evaluate_spending_policy(_base_round(report_value=75.0))
    policy = result["agent_spending_policy"]
    assert policy["approval_policy"] == "auto"
    assert policy["requires_human_approval"] is False
    assert policy["reason"] == "low_risk_low_value_auto_approved"
    assert policy["service"] == "sika-route"
    assert policy["max_auto_spend"] == 100.0


def test_high_value_requires_human_approval():
    result = evaluate_spending_policy(_base_round(report_value=500.0))
    policy = result["agent_spending_policy"]
    assert policy["approval_policy"] == "human_required"
    assert policy["requires_human_approval"] is True
    assert policy["reason"] == "high_value_report"


def test_risk_agent_flagged_requires_human_approval():
    result = evaluate_spending_policy(_base_round(risk_agent_flagged=True, report_value=40.0))
    policy = result["agent_spending_policy"]
    assert policy["approval_policy"] == "human_required"
    assert policy["reason"] == "risk_agent_flagged"


def test_unsupported_corridor_blocked():
    result = evaluate_spending_policy(_base_round(corridor="US-XX"))
    policy = result["agent_spending_policy"]
    assert policy["approval_policy"] == "blocked"
    assert policy["reason"] == "unsupported_corridor"


def test_missing_disclaimer_blocked():
    result = evaluate_spending_policy(_base_round(disclaimer=""))
    policy = result["agent_spending_policy"]
    assert policy["approval_policy"] == "blocked"
    assert policy["reason"] == "missing_disclaimer"


def test_policy_hash_is_sha256_of_canonical_json():
    result = evaluate_spending_policy(_base_round())
    policy = result["agent_spending_policy"]
    expected = sha256_hex(canonical_json(policy))
    assert result["policy_hash"] == expected
    assert result["kaspa_ready_covenant_policy_hash"] == expected


def test_policy_is_deterministic():
    round_a = _base_round(market_id="mkt_det_001")
    round_b = _base_round(market_id="mkt_det_001")
    assert evaluate_spending_policy(round_a) == evaluate_spending_policy(round_b)


def test_policy_serialisable_as_json():
    result = evaluate_spending_policy(_base_round())
    serialised = json.dumps(result["agent_spending_policy"], sort_keys=True)
    assert json.loads(serialised)["market_id"] == "mkt_test_001"


def test_delivery_hash_included_when_available():
    result = evaluate_spending_policy(_base_round())
    assert "delivery_hash" in result["agent_spending_policy"]


def test_delivery_hash_omitted_when_unavailable():
    result = evaluate_spending_policy(_base_round(delivery_payload=None))
    assert "delivery_hash" not in result["agent_spending_policy"]


def test_required_policy_fields_present():
    result = evaluate_spending_policy(_base_round())
    policy = result["agent_spending_policy"]
    required = {
        "market_id",
        "service",
        "buyer_agent",
        "selected_seller_agent",
        "max_auto_spend",
        "spend_currency",
        "risk_level",
        "requires_human_approval",
        "reason",
        "approval_policy",
        "request_hash",
        "bid_hash",
        "disclaimer",
    }
    assert required.issubset(policy.keys())


def test_kaspa_label_constant():
    result = evaluate_spending_policy(_base_round())
    assert result["kaspa_ready_covenant_policy_hash_label"] == KASPA_POLICY_HASH_LABEL


def test_demo_scenarios_cover_all_rules(client):
    auto = run_demo_scenario("auto_low_value")
    assert auto["agent_spending_policy"]["approval_policy"] == "auto"

    high = run_demo_scenario("high_value_human")
    assert high["agent_spending_policy"]["approval_policy"] == "human_required"

    risk = run_demo_scenario("risk_flagged")
    assert risk["agent_spending_policy"]["approval_policy"] == "human_required"

    corridor = run_demo_scenario("unsupported_corridor")
    assert corridor["agent_spending_policy"]["approval_policy"] == "blocked"

    disclaimer = run_demo_scenario("missing_disclaimer")
    assert disclaimer["agent_spending_policy"]["approval_policy"] == "blocked"


def test_api_market_round_endpoint(client):
    body = {
        "market_id": "mkt_api_001",
        "buyer_agent": "coral-buyer",
        "selected_seller_agent": "sika-seller",
        "corridor": "EU-KE",
        "report_value": 90.0,
        "risk_level": "low",
        "request_payload": {"route": "EU-KE", "amount": 90.0},
        "bid_payload": {"seller": "sika-seller", "fee_bps": 70},
    }
    resp = client.post("/sika-route/market/round", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_spending_policy" in data
    assert "policy_hash" in data
    assert data["kaspa_ready_covenant_policy_hash_label"] == KASPA_POLICY_HASH_LABEL


def test_api_demo_scenarios_endpoint(client):
    resp = client.get("/sika-route/market/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()["scenarios"]
    assert len(scenarios) == len(DEMO_SCENARIOS)


def test_api_run_demo_scenario(client):
    resp = client.post("/sika-route/market/scenarios/auto_low_value/run")
    assert resp.status_code == 200
    assert resp.json()["agent_spending_policy"]["approval_policy"] == "auto"


def test_run_market_round_produces_policy_for_every_round():
    for scenario in DEMO_SCENARIOS.values():
        result = run_market_round(scenario)
        assert "agent_spending_policy" in result
        assert "policy_hash" in result
