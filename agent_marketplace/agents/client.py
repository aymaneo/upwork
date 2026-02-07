"""Client agent nodes — posts jobs and selects providers."""

from __future__ import annotations

from agent_marketplace.agents.base import BaseAgent
from agent_marketplace.state import MarketplaceState

_client_agent = BaseAgent(
    persona=(
        "You are a client agent in an AI compute marketplace. "
        "You post jobs, evaluate bids from provider agents, and select "
        "the best provider based on price and quality. Be concise."
    )
)


def post_job_node(state: MarketplaceState) -> dict:
    """Post a job to the marketplace."""
    desc = state["job_description"]
    budget = state["job_budget_usdc"]

    reasoning = _client_agent.think(
        f"You are posting a job on the AI agent marketplace.\n"
        f"Job: {desc}\n"
        f"Budget: ${budget:.4f} USDC\n\n"
        f"Write a brief 1-2 sentence announcement for this job posting."
    )

    return {
        "marketplace_status": "bidding",
        "events_log": [
            f"[CLIENT] Job posted: {desc} (budget: ${budget:.4f} USDC)",
            f"[CLIENT] {reasoning}",
        ],
    }


def select_provider_node(state: MarketplaceState) -> dict:
    """Select the cheapest provider from bids."""
    bids = state["bids"]
    budget = state["job_budget_usdc"]

    bids_text = "\n".join(
        f"- {b['provider_name']}: ${b['price_usdc']:.4f} — {b['reasoning']}"
        for b in bids
    )

    reasoning = _client_agent.think(
        f"You received these bids for your job (budget ${budget:.4f}):\n"
        f"{bids_text}\n\n"
        f"Select the cheapest bid that's within budget. "
        f"State which provider you choose and why in 1-2 sentences."
    )

    # Select cheapest within budget
    valid = [b for b in bids if b["price_usdc"] <= budget]
    if not valid:
        return {
            "marketplace_status": "failed",
            "events_log": [f"[CLIENT] No bids within budget. {reasoning}"],
        }

    chosen = min(valid, key=lambda b: b["price_usdc"])

    return {
        "selected_provider": chosen["provider_name"],
        "selected_price": chosen["price_usdc"],
        "marketplace_status": "paying",
        "events_log": [
            f"[CLIENT] Selected {chosen['provider_name']} "
            f"at ${chosen['price_usdc']:.4f} USDC",
            f"[CLIENT] {reasoning}",
        ],
    }
