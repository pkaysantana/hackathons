"""SikaRoute Market — Kaspa-ready agent spending policy hook (no live Kaspa).

CoralOS coordinates buyer/seller/risk agents; Solana devnet handles the current
escrow demo. This module produces a deterministic ``agent_spending_policy`` JSON
object for every market round so a future Kaspa SikaGuard covenant can enforce
autonomous-agent spend limits without replacing Solana escrow in the MVP phase.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

SERVICE = "sika-route"
SPEND_CURRENCY = "USD"
MAX_AUTO_SPEND = 100.0
LOW_VALUE_MAX = 100.0
HIGH_VALUE_MIN = 500.0

SUPPORTED_CORRIDORS = frozenset({"US-KE", "US-NG", "UK-KE", "EU-KE"})

RiskLevel = Literal["low", "medium", "high"]
ApprovalPolicy = Literal["auto", "human_required", "blocked"]

KASPA_POLICY_HASH_LABEL = "Kaspa-ready covenant policy hash"

DEFAULT_DISCLAIMER = (
    "SikaRoute demo — testnet only. No real user funds. No personal data on-chain."
)


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialisation for covenant hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(payload))


class MarketRoundInput(BaseModel):
    market_id: str
    buyer_agent: str
    selected_seller_agent: str
    corridor: str
    report_value: float = Field(ge=0)
    spend_currency: str = SPEND_CURRENCY
    risk_level: RiskLevel
    risk_agent_flagged: bool = False
    request_payload: dict[str, Any]
    bid_payload: dict[str, Any]
    delivery_payload: dict[str, Any] | None = None
    disclaimer: str | None = DEFAULT_DISCLAIMER


def evaluate_spending_policy(round_input: MarketRoundInput) -> dict[str, Any]:
    """Apply SikaRoute spending rules and return policy + policy_hash."""
    request_hash = payload_hash(round_input.request_payload)
    bid_hash = payload_hash(round_input.bid_payload)
    delivery_hash = (
        payload_hash(round_input.delivery_payload)
        if round_input.delivery_payload is not None
        else None
    )

    disclaimer = (round_input.disclaimer or "").strip()
    corridor = round_input.corridor.strip().upper()

    if corridor not in SUPPORTED_CORRIDORS:
        approval_policy: ApprovalPolicy = "blocked"
        requires_human_approval = True
        reason = "unsupported_corridor"
    elif not disclaimer:
        approval_policy = "blocked"
        requires_human_approval = True
        reason = "missing_disclaimer"
    elif round_input.risk_agent_flagged:
        approval_policy = "human_required"
        requires_human_approval = True
        reason = "risk_agent_flagged"
    elif round_input.report_value >= HIGH_VALUE_MIN:
        approval_policy = "human_required"
        requires_human_approval = True
        reason = "high_value_report"
    elif round_input.risk_level == "low" and round_input.report_value <= LOW_VALUE_MAX:
        approval_policy = "auto"
        requires_human_approval = False
        reason = "low_risk_low_value_auto_approved"
    else:
        approval_policy = "human_required"
        requires_human_approval = True
        reason = "requires_human_review"

    policy: dict[str, Any] = {
        "market_id": round_input.market_id,
        "service": SERVICE,
        "buyer_agent": round_input.buyer_agent,
        "selected_seller_agent": round_input.selected_seller_agent,
        "max_auto_spend": MAX_AUTO_SPEND,
        "spend_currency": round_input.spend_currency,
        "risk_level": round_input.risk_level,
        "requires_human_approval": requires_human_approval,
        "reason": reason,
        "approval_policy": approval_policy,
        "request_hash": request_hash,
        "bid_hash": bid_hash,
        "disclaimer": disclaimer,
    }
    if delivery_hash is not None:
        policy["delivery_hash"] = delivery_hash

    policy_hash = sha256_hex(canonical_json(policy))

    return {
        "agent_spending_policy": policy,
        "policy_hash": policy_hash,
        "kaspa_ready_covenant_policy_hash": policy_hash,
        "kaspa_ready_covenant_policy_hash_label": KASPA_POLICY_HASH_LABEL,
    }


def run_market_round(round_input: MarketRoundInput) -> dict[str, Any]:
    """Execute one SikaRoute market round and attach spending policy metadata."""
    result = evaluate_spending_policy(round_input)
    return {
        "market_id": round_input.market_id,
        "corridor": round_input.corridor.strip().upper(),
        "report_value": round_input.report_value,
        "buyer_agent": round_input.buyer_agent,
        "selected_seller_agent": round_input.selected_seller_agent,
        **result,
    }


DEMO_SCENARIOS: dict[str, MarketRoundInput] = {
    "auto_low_value": MarketRoundInput(
        market_id="mkt_demo_auto_001",
        buyer_agent="coral-buyer-routing",
        selected_seller_agent="sika-seller-nairobi",
        corridor="US-KE",
        report_value=75.0,
        risk_level="low",
        request_payload={
            "route": "US-KE",
            "amount": 75.0,
            "purpose": "clinical_handoff_batch",
        },
        bid_payload={
            "seller": "sika-seller-nairobi",
            "fee_bps": 85,
            "eta_minutes": 12,
        },
        delivery_payload={"status": "delivered", "confirmation": "demo-conf-001"},
        disclaimer=DEFAULT_DISCLAIMER,
    ),
    "high_value_human": MarketRoundInput(
        market_id="mkt_demo_high_002",
        buyer_agent="coral-buyer-treasury",
        selected_seller_agent="sika-seller-lagos",
        corridor="US-NG",
        report_value=750.0,
        risk_level="low",
        request_payload={
            "route": "US-NG",
            "amount": 750.0,
            "purpose": "partner_lab_handoff",
        },
        bid_payload={
            "seller": "sika-seller-lagos",
            "fee_bps": 72,
            "eta_minutes": 18,
        },
        delivery_payload={"status": "pending", "confirmation": None},
        disclaimer=DEFAULT_DISCLAIMER,
    ),
    "risk_flagged": MarketRoundInput(
        market_id="mkt_demo_risk_003",
        buyer_agent="coral-buyer-routing",
        selected_seller_agent="sika-seller-nairobi",
        corridor="US-KE",
        report_value=60.0,
        risk_level="medium",
        risk_agent_flagged=True,
        request_payload={
            "route": "US-KE",
            "amount": 60.0,
            "purpose": "new_counterparty",
        },
        bid_payload={
            "seller": "sika-seller-nairobi",
            "fee_bps": 95,
            "eta_minutes": 20,
        },
        disclaimer=DEFAULT_DISCLAIMER,
    ),
    "unsupported_corridor": MarketRoundInput(
        market_id="mkt_demo_block_corridor",
        buyer_agent="coral-buyer-routing",
        selected_seller_agent="sika-seller-unknown",
        corridor="US-XX",
        report_value=40.0,
        risk_level="low",
        request_payload={"route": "US-XX", "amount": 40.0},
        bid_payload={"seller": "sika-seller-unknown", "fee_bps": 100},
        disclaimer=DEFAULT_DISCLAIMER,
    ),
    "missing_disclaimer": MarketRoundInput(
        market_id="mkt_demo_block_disclaimer",
        buyer_agent="coral-buyer-routing",
        selected_seller_agent="sika-seller-nairobi",
        corridor="UK-KE",
        report_value=45.0,
        risk_level="low",
        request_payload={"route": "UK-KE", "amount": 45.0},
        bid_payload={"seller": "sika-seller-nairobi", "fee_bps": 80},
        disclaimer="",
    ),
}


def list_demo_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": scenario_id,
            "market_id": scenario.market_id,
            "corridor": scenario.corridor,
            "report_value": scenario.report_value,
            "risk_level": scenario.risk_level,
            "risk_agent_flagged": scenario.risk_agent_flagged,
            "description": _scenario_description(scenario_id),
        }
        for scenario_id, scenario in DEMO_SCENARIOS.items()
    ]


def _scenario_description(scenario_id: str) -> str:
    descriptions = {
        "auto_low_value": "Low-risk, low-value report — auto-approved spend path.",
        "high_value_human": "High-value report — human approval required.",
        "risk_flagged": "Risk-agent flag — human approval required.",
        "unsupported_corridor": "Unsupported corridor — blocked.",
        "missing_disclaimer": "Missing disclaimer — blocked.",
    }
    return descriptions.get(scenario_id, scenario_id)


def run_demo_scenario(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in DEMO_SCENARIOS:
        raise KeyError(scenario_id)
    return run_market_round(DEMO_SCENARIOS[scenario_id])


def run_all_demo_rounds() -> list[dict[str, Any]]:
    return [run_market_round(scenario) for scenario in DEMO_SCENARIOS.values()]
