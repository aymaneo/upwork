"""Budget validation guardrails before payment execution."""

from __future__ import annotations

from agent_marketplace.state import MarketplaceState


def validate_budget_node(state: MarketplaceState) -> dict:
    """Validate that the selected bid price is within the job budget."""
    budget = state["job_budget_usdc"]
    price = state["selected_price"]
    provider = state["selected_provider"]

    if price > budget:
        return {
            "budget_valid": False,
            "marketplace_status": "failed",
            "events_log": [
                f"[GUARDRAIL] REJECTED: {provider} bid ${price:.2f} "
                f"exceeds budget ${budget:.2f} USDC",
            ],
        }

    return {
        "budget_valid": True,
        "events_log": [
            f"[GUARDRAIL] APPROVED: {provider} bid ${price:.2f} "
            f"is within budget ${budget:.2f} USDC",
        ],
    }


def budget_is_valid(state: MarketplaceState) -> str:
    """Conditional edge: route based on budget validation result."""
    if state.get("budget_valid"):
        return "valid"
    return "invalid"
