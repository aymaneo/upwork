"""LangGraph workflow: wires all agent nodes and conditional edges."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_marketplace.agents.client import (
    judge_work_node,
    post_job_node,
    select_provider_node,
)
from agent_marketplace.agents.provider import (
    bid_claude_node,
    bid_gpt4_node,
    close_bidding_node,
    deliver_work_node,
)
from agent_marketplace.config import PAYMENT_MODE
from agent_marketplace.guardrails.validators import (
    budget_is_valid,
    validate_budget_node,
)
from agent_marketplace.payments.mock import MockPaymentProvider
from agent_marketplace.state import MarketplaceState

# Shared payment provider instance (replaced at runtime for Plasma mode)
_payment_provider = MockPaymentProvider()


def set_payment_provider(provider: MockPaymentProvider) -> None:
    global _payment_provider
    _payment_provider = provider


def escrow_hold_node(state: MarketplaceState) -> dict:
    """Hold funds in escrow before work begins."""
    provider = state["selected_provider"]
    price = state["selected_price"]

    if PAYMENT_MODE == "plasma":
        # Plasma mode: conceptual hold only — no on-chain tx yet.
        return {
            "escrow_status": "held",
            "marketplace_status": "delivering",
            "events_log": [
                f"[ESCROW] Conceptual hold of ${price:.4f} USDC for {provider}",
                f"[ESCROW] Funds remain in client wallet until judge approves.",
            ],
        }

    # Mock mode: actual transfer client → escrow-agent
    try:
        receipt = _payment_provider.transfer(
            from_addr="client-agent",
            to_addr="escrow-agent",
            amount_usdc=price,
        )
        return {
            "escrow_status": "held",
            "escrow_receipt": receipt,
            "marketplace_status": "delivering",
            "events_log": [
                f"[ESCROW] Held ${price:.4f} USDC in escrow for {provider}",
                f"[ESCROW] Hold TX: {receipt['tx_hash']} on {receipt['chain']}",
            ],
        }
    except Exception as e:
        return {
            "escrow_status": "failed",
            "marketplace_status": "failed",
            "events_log": [f"[ESCROW] Hold FAILED: {e}"],
        }


def escrow_hold_succeeded(state: MarketplaceState) -> str:
    """Conditional edge: route based on escrow hold result."""
    if state.get("escrow_status") == "held":
        return "held"
    return "failed"


def judge_verdict_router(state: MarketplaceState) -> str:
    """Conditional edge: route based on judge verdict."""
    if state.get("judge_verdict") == "approved":
        return "approved"
    return "rejected"


def escrow_release_node(state: MarketplaceState) -> dict:
    """Release escrowed funds to the provider after judge approval."""
    provider = state["selected_provider"]
    price = state["selected_price"]
    to_addr = provider.lower().replace(" ", "-")

    if PAYMENT_MODE == "plasma":
        # Plasma mode: this is the actual on-chain transfer.
        try:
            receipt = _payment_provider.transfer(
                from_addr="client-agent",
                to_addr=to_addr,
                amount_usdc=price,
            )
            return {
                "escrow_status": "released",
                "payment_receipt": receipt,
                "payment_status": "confirmed",
                "marketplace_status": "complete",
                "events_log": [
                    f"[ESCROW] Released ${price:.4f} USDC to {provider}",
                    f"[ESCROW] TX: {receipt['tx_hash']} on {receipt['chain']}",
                ],
            }
        except Exception as e:
            return {
                "payment_status": "failed",
                "marketplace_status": "failed",
                "events_log": [f"[ESCROW] Release FAILED: {e}"],
            }

    # Mock mode: transfer escrow-agent → provider
    try:
        receipt = _payment_provider.transfer(
            from_addr="escrow-agent",
            to_addr=to_addr,
            amount_usdc=price,
        )
        return {
            "escrow_status": "released",
            "payment_receipt": receipt,
            "payment_status": "confirmed",
            "marketplace_status": "complete",
            "events_log": [
                f"[ESCROW] Released ${price:.4f} USDC to {provider}",
                f"[ESCROW] TX: {receipt['tx_hash']} on {receipt['chain']}",
            ],
        }
    except Exception as e:
        return {
            "payment_status": "failed",
            "marketplace_status": "failed",
            "events_log": [f"[ESCROW] Release FAILED: {e}"],
        }


def escrow_refund_node(state: MarketplaceState) -> dict:
    """Refund escrowed funds to the client after judge rejection."""
    price = state["selected_price"]

    if PAYMENT_MODE == "plasma":
        # Plasma mode: no-op — funds never left the client wallet.
        return {
            "escrow_status": "refunded",
            "marketplace_status": "failed",
            "events_log": [
                f"[ESCROW] Refund: ${price:.4f} USDC — funds never left client wallet.",
            ],
        }

    # Mock mode: transfer escrow-agent → client-agent
    try:
        receipt = _payment_provider.transfer(
            from_addr="escrow-agent",
            to_addr="client-agent",
            amount_usdc=price,
        )
        return {
            "escrow_status": "refunded",
            "marketplace_status": "failed",
            "events_log": [
                f"[ESCROW] Refunded ${price:.4f} USDC to client",
                f"[ESCROW] Refund TX: {receipt['tx_hash']} on {receipt['chain']}",
            ],
        }
    except Exception as e:
        return {
            "escrow_status": "refunded",
            "marketplace_status": "failed",
            "events_log": [f"[ESCROW] Refund error: {e}"],
        }


def end_failed_node(state: MarketplaceState) -> dict:
    """Terminal node for failed workflows."""
    return {
        "marketplace_status": "failed",
        "events_log": ["[MARKETPLACE] Workflow ended due to failure."],
    }


def build_graph() -> StateGraph:
    """Construct the marketplace LangGraph workflow."""
    graph = StateGraph(MarketplaceState)

    # Add nodes
    graph.add_node("post_job", post_job_node)
    graph.add_node("bid_gpt4", bid_gpt4_node)
    graph.add_node("bid_claude", bid_claude_node)
    graph.add_node("close_bidding", close_bidding_node)
    graph.add_node("select_provider", select_provider_node)
    graph.add_node("validate_budget", validate_budget_node)
    graph.add_node("escrow_hold", escrow_hold_node)
    graph.add_node("deliver_work", deliver_work_node)
    graph.add_node("judge_work", judge_work_node)
    graph.add_node("escrow_release", escrow_release_node)
    graph.add_node("escrow_refund", escrow_refund_node)
    graph.add_node("end_failed", end_failed_node)

    # Linear edges
    graph.set_entry_point("post_job")
    graph.add_edge("post_job", "bid_gpt4")
    graph.add_edge("bid_gpt4", "bid_claude")
    graph.add_edge("bid_claude", "close_bidding")
    graph.add_edge("close_bidding", "select_provider")
    graph.add_edge("select_provider", "validate_budget")

    # Conditional: budget validation
    graph.add_conditional_edges(
        "validate_budget",
        budget_is_valid,
        {"valid": "escrow_hold", "invalid": "end_failed"},
    )

    # Conditional: escrow hold result
    graph.add_conditional_edges(
        "escrow_hold",
        escrow_hold_succeeded,
        {"held": "deliver_work", "failed": "end_failed"},
    )

    # After work delivery → judge
    graph.add_edge("deliver_work", "judge_work")

    # Conditional: judge verdict
    graph.add_conditional_edges(
        "judge_work",
        judge_verdict_router,
        {"approved": "escrow_release", "rejected": "escrow_refund"},
    )

    # Terminal edges
    graph.add_edge("escrow_release", END)
    graph.add_edge("escrow_refund", END)
    graph.add_edge("end_failed", END)

    return graph
