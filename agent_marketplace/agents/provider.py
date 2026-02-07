"""Provider agent nodes — bid on jobs and deliver work."""

from __future__ import annotations

from agent_marketplace.agents.base import BaseAgent
from agent_marketplace.state import Bid, MarketplaceState

_gpt4_agent = BaseAgent(
    persona=(
        "You are 'GPT-4 Provider', an AI compute provider in a decentralized marketplace. "
        "You specialize in high-quality text analysis and summarization. "
        "You are confident and slightly premium-priced. Be concise."
    )
)

_claude_agent = BaseAgent(
    persona=(
        "You are 'Claude Provider', an AI compute provider in a decentralized marketplace. "
        "You specialize in efficient, accurate text processing at competitive prices. "
        "You are friendly and cost-effective. Be concise."
    )
)


def bid_gpt4_node(state: MarketplaceState) -> dict:
    """GPT-4 provider submits a bid."""
    desc = state["job_description"]
    budget = state["job_budget_usdc"]

    reasoning = _gpt4_agent.think(
        f"A client posted a job on the marketplace:\n"
        f"Job: {desc}\n"
        f"Budget: ${budget:.2f} USDC\n\n"
        f"You want to bid $0.005 for this job. "
        f"Write a 1-2 sentence pitch for why the client should pick you."
    )

    bid: Bid = {
        "provider_name": "GPT-4 Provider",
        "price_usdc": 0.005,
        "reasoning": reasoning,
    }

    return {
        "bids": [bid],
        "events_log": [
            f"[GPT-4 PROVIDER] Bid: $0.005 USDC",
            f"[GPT-4 PROVIDER] {reasoning}",
        ],
    }


def bid_claude_node(state: MarketplaceState) -> dict:
    """Claude provider submits a bid."""
    desc = state["job_description"]
    budget = state["job_budget_usdc"]

    reasoning = _claude_agent.think(
        f"A client posted a job on the marketplace:\n"
        f"Job: {desc}\n"
        f"Budget: ${budget:.2f} USDC\n\n"
        f"You want to bid $0.003 for this job. "
        f"Write a 1-2 sentence pitch for why the client should pick you."
    )

    bid: Bid = {
        "provider_name": "Claude Provider",
        "price_usdc": 0.003,
        "reasoning": reasoning,
    }

    return {
        "bids": [bid],
        "events_log": [
            f"[CLAUDE PROVIDER] Bid: $0.003 USDC",
            f"[CLAUDE PROVIDER] {reasoning}",
        ],
    }


def close_bidding_node(state: MarketplaceState) -> dict:
    """Close the bidding phase."""
    num = len(state["bids"])
    return {
        "events_log": [f"[MARKETPLACE] Bidding closed. {num} bids received."],
    }


def deliver_work_node(state: MarketplaceState) -> dict:
    """Selected provider delivers the work."""
    provider = state["selected_provider"]
    desc = state["job_description"]

    agent = _claude_agent if "Claude" in provider else _gpt4_agent

    result = agent.think(
        f"You won the job! The client is paying you to do this task:\n"
        f"{desc}\n\n"
        f"Deliver the work now. Provide a complete, high-quality response."
    )

    return {
        "work_result": result,
        "marketplace_status": "complete",
        "events_log": [
            f"[{provider.upper()}] Work delivered successfully.",
        ],
    }
