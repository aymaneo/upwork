"""Client agent nodes — posts jobs and selects providers."""

from __future__ import annotations

import json

from guardrails import Guard
from guardrails.errors import ValidationError

from agent_marketplace.agents.base import BaseAgent
from agent_marketplace.guardrails.validators import RubricValidator
from agent_marketplace.state import MarketplaceState

_client_agent = BaseAgent(
    persona=(
        "You are a client agent that delegates tasks to specialized providers "
        "because you lack the required capability — no browser, no GPU, or "
        "wrong model. You post tasks, evaluate bids, and select the best "
        "provider to outsource to. Be concise."
    )
)

_judge_agent = BaseAgent(
    persona=(
        "You are an impartial judge that evaluates whether outsourced work "
        "meets what the delegating agent needed. The client delegated this "
        "task because it lacked the capability to do it itself — your job is "
        "to verify the provider delivered. Be fair but rigorous. Be concise."
    )
)


def post_job_node(state: MarketplaceState) -> dict:
    """Post a job to the marketplace."""
    desc = state["job_description"]
    budget = state["job_budget_xpl"]

    reasoning = _client_agent.think(
        f"You are posting a job on the AI agent marketplace.\n"
        f"Job: {desc}\n"
        f"Budget: {budget:.4f} XPL\n\n"
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
            f"[CLIENT] Job posted: {desc} (budget: {budget:.4f} XPL)",
            f"[CLIENT] Job type: {job_type.upper()}",
            f"[CLIENT] {reasoning}",
        ],
    }


def select_provider_node(state: MarketplaceState) -> dict:
    """Select the cheapest provider from bids."""
    bids = state["bids"]
    budget = state["job_budget_xpl"]

    bids_text = "\n".join(
        f"- {b['provider_name']}: {b['price_xpl']:.4f} XPL — {b['reasoning']}"
        for b in bids
    )

    reasoning = _client_agent.think(
        f"You received these bids for your job (budget {budget:.4f} XPL):\n"
        f"{bids_text}\n\n"
        f"Select the cheapest bid that's within budget. "
        f"State which provider you choose and why in 1-2 sentences."
    )

    # Select cheapest within budget
    valid = [b for b in bids if b["price_xpl"] <= budget]
    if not valid:
        return {
            "marketplace_status": "failed",
            "events_log": [f"[CLIENT] No bids within budget. {reasoning}"],
        }

    chosen = min(valid, key=lambda b: b["price_xpl"])

    return {
        "selected_provider": chosen["provider_name"],
        "selected_price": chosen["price_xpl"],
        "marketplace_status": "paying",
        "events_log": [
            f"[CLIENT] Selected {chosen['provider_name']} "
            f"at {chosen['price_xpl']:.4f} XPL",
            f"[CLIENT] {reasoning}",
        ],
    }


_RUBRIC_PROMPT = (
    "You are judging whether delivered work meets the job requirements.\n\n"
    "JOB DESCRIPTION:\n{desc}\n\n"
    "DELIVERED WORK:\n{work}\n\n"
    "Score each criterion from 0.0 (worst) to 1.0 (best).\n"
    "Respond with ONLY valid JSON (no markdown, no extra text):\n"
    '{{"completeness": <0.0-1.0>, "relevance": <0.0-1.0>, '
    '"quality": <0.0-1.0>, "reasoning": "<1-2 sentence explanation>"}}'
)

_RUBRIC_RETRY_PROMPT = (
    "Your previous response was not valid JSON. You MUST respond with "
    "ONLY this exact JSON structure — no markdown fences, no extra text:\n"
    '{{"completeness": <float 0.0-1.0>, "relevance": <float 0.0-1.0>, '
    '"quality": <float 0.0-1.0>, "reasoning": "<string>"}}\n\n'
    "JOB DESCRIPTION:\n{desc}\n\n"
    "DELIVERED WORK:\n{work}\n\n"
    "Respond now:"
)


def judge_work_node(state: MarketplaceState) -> dict:
    """Judge evaluates delivered work quality using a structured rubric."""
    desc = state["job_description"]
    result = state.get("work_result", "")
    work = result[:2000]

    guard = Guard().use(RubricValidator(), on="output")

    # First attempt
    response = _judge_agent.think(
        _RUBRIC_PROMPT.format(desc=desc, work=work)
    )

    try:
        guard.validate(response)
        data = json.loads(response)
    except (ValidationError, json.JSONDecodeError):
        # Retry once with stricter prompt
        response = _judge_agent.think(
            _RUBRIC_RETRY_PROMPT.format(desc=desc, work=work)
        )
        try:
            guard.validate(response)
            data = json.loads(response)
        except (ValidationError, json.JSONDecodeError):
            # Default to rejected on persistent failure
            return {
                "judge_scores": {"completeness": 0.0, "relevance": 0.0, "quality": 0.0},
                "judge_verdict": "rejected",
                "judge_reasoning": "Judge validation failed — defaulting to rejected.",
                "marketplace_status": "judging",
                "events_log": [
                    "[JUDGE] Rubric validation failed after retry",
                    "[JUDGE] Verdict: REJECTED (default — invalid response)",
                ],
            }

    scores = {
        "completeness": float(data["completeness"]),
        "relevance": float(data["relevance"]),
        "quality": float(data["quality"]),
    }
    average = sum(scores.values()) / len(scores)
    verdict = "approved" if average >= 0.6 else "rejected"
    reasoning = data["reasoning"]

    return {
        "judge_scores": scores,
        "judge_verdict": verdict,
        "judge_reasoning": reasoning,
        "marketplace_status": "judging",
        "events_log": [
            f"[JUDGE] Scores — completeness: {scores['completeness']:.1f}, "
            f"relevance: {scores['relevance']:.1f}, quality: {scores['quality']:.1f} "
            f"(avg: {average:.2f})",
            f"[JUDGE] Verdict: {verdict.upper()}",
            f"[JUDGE] {reasoning}",
        ],
    }
