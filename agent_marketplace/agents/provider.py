"""Provider agent nodes — bid on jobs and deliver work."""

from __future__ import annotations

import asyncio
import json

from agent_marketplace.agents.base import BaseAgent
from agent_marketplace.agents.browser_agent import run_browser_task
from agent_marketplace.config import BROWSER_HEADLESS
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


def _parse_bid(response: str, budget: float) -> tuple[float, str]:
    """Extract price and reasoning from an LLM JSON response."""
    try:
        data = json.loads(response)
        price = float(data["price"])
        reasoning = data.get("reasoning", "")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        # Fallback: use half the budget
        price = round(budget * 0.5, 4)
        reasoning = response
    # Clamp to 90% of budget
    price = min(price, round(budget * 0.9, 6))
    return price, reasoning


def _bid_prompt(desc: str, budget: float, persona_hint: str) -> str:
    max_bid = round(budget * 0.9, 6)
    return (
        f"A client posted a job on the marketplace:\n"
        f"Job: {desc}\n"
        f"Budget: ${budget} USDC\n\n"
        f"RULES:\n"
        f"- You MUST bid strictly LESS than the budget.\n"
        f"- Your price must be between $0 and ${max_bid} USDC (max 90% of budget).\n"
        f"- {persona_hint}\n\n"
        f"Respond with ONLY valid JSON (no markdown, no extra text):\n"
        f'{{"price": <your bid as a number>, "reasoning": "<1-2 sentence pitch>"}}'
    )


def bid_gpt4_node(state: MarketplaceState) -> dict:
    """GPT-4 provider submits a bid."""
    desc = state["job_description"]
    budget = state["job_budget_usdc"]

    response = _gpt4_agent.think(
        _bid_prompt(
            desc,
            budget,
            "You value quality and tend to price on the higher end of the allowed range.",
        )
    )

    price, reasoning = _parse_bid(response, budget)

    bid: Bid = {
        "provider_name": "GPT-4 Provider",
        "price_usdc": price,
        "reasoning": reasoning,
    }

    return {
        "bids": [bid],
        "events_log": [
            f"[GPT-4 PROVIDER] Bid: ${price} USDC",
            f"[GPT-4 PROVIDER] {reasoning}",
        ],
    }


def bid_claude_node(state: MarketplaceState) -> dict:
    """Claude provider submits a bid."""
    desc = state["job_description"]
    budget = state["job_budget_usdc"]

    response = _claude_agent.think(
        _bid_prompt(
            desc,
            budget,
            "You are cost-effective and tend to undercut competitors with a lower price.",
        )
    )

    price, reasoning = _parse_bid(response, budget)

    bid: Bid = {
        "provider_name": "Claude Provider",
        "price_usdc": price,
        "reasoning": reasoning,
    }

    return {
        "bids": [bid],
        "events_log": [
            f"[CLAUDE PROVIDER] Bid: ${price} USDC",
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

    if state.get("job_type") == "browser":
        result = asyncio.run(run_browser_task(desc, headless=BROWSER_HEADLESS))
    else:
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
