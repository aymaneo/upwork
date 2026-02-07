"""Client agent nodes — posts jobs and selects providers."""

from __future__ import annotations

import json

from agent_marketplace.agents.base import BaseAgent
from agent_marketplace.state import MarketplaceState

_client_agent = BaseAgent(
    persona=(
        "You are a client agent in an AI compute marketplace. "
        "You post jobs, evaluate bids from provider agents, and select "
        "the best provider based on price and quality. Be concise."
    )
)

_judge_agent = BaseAgent(
    persona=(
        "You are an impartial quality judge in an AI compute marketplace. "
        "You evaluate whether delivered work meets the job requirements. "
        "You are fair but rigorous. Be concise."
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

    # Classify whether this job needs a real browser or is a shopping task
    classification = _client_agent.think(
        f"Classify this job into exactly one category:\n"
        f"- 'shopping' = buying groceries or products from an online store\n"
        f"- 'browser' = any other task requiring a real web browser\n"
        f"- 'text' = pure text/analysis task, no browser needed\n\n"
        f"Job: {desc}\n\n"
        f"Respond with ONLY one word: 'text', 'browser', or 'shopping'."
    )
    raw = classification.strip().lower()
    if "shopping" in raw:
        job_type = "shopping"
    elif "browser" in raw:
        job_type = "browser"
    else:
        job_type = "text"

    return {
        "job_type": job_type,
        "marketplace_status": "bidding",
        "events_log": [
            f"[CLIENT] Job posted: {desc} (budget: ${budget:.4f} USDC)",
            f"[CLIENT] Job type: {job_type.upper()}",
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


def judge_work_node(state: MarketplaceState) -> dict:
    """Judge evaluates delivered work quality."""
    desc = state["job_description"]
    result = state.get("work_result", "")

    response = _judge_agent.think(
        f"You are judging whether delivered work meets the job requirements.\n\n"
        f"JOB DESCRIPTION:\n{desc}\n\n"
        f"DELIVERED WORK:\n{result[:2000]}\n\n"
        f"Evaluate completeness, relevance, and quality.\n"
        f"Respond with ONLY valid JSON (no markdown, no extra text):\n"
        f'{{"verdict": "approved" or "rejected", "reasoning": "<1-2 sentence explanation>"}}'
    )

    try:
        data = json.loads(response)
        verdict = data.get("verdict", "approved").lower()
        reasoning = data.get("reasoning", "")
        if verdict not in ("approved", "rejected"):
            verdict = "approved"
    except (json.JSONDecodeError, AttributeError):
        verdict = "approved"
        reasoning = "Judge parse failed — defaulting to approved."

    return {
        "judge_verdict": verdict,
        "judge_reasoning": reasoning,
        "marketplace_status": "judging",
        "events_log": [
            f"[JUDGE] Verdict: {verdict.upper()}",
            f"[JUDGE] {reasoning}",
        ],
    }
