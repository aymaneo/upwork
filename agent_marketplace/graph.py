"""LangGraph workflow: wires all agent nodes and conditional edges."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_marketplace.agents.client import post_job_node, select_provider_node
from agent_marketplace.agents.provider import (
    bid_claude_node,
    bid_gpt4_node,
    close_bidding_node,
    deliver_work_node,
)
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


def execute_payment_node(state: MarketplaceState) -> dict:
    """Execute payment from client to selected provider."""
    provider = state["selected_provider"]
    price = state["selected_price"]

    to_addr = "provider-claude" if "Claude" in provider else "provider-gpt4"

    try:
        receipt = _payment_provider.transfer(
            from_addr="client-agent",
            to_addr=to_addr,
            amount_usdc=price,
        )
        return {
            "payment_receipt": receipt,
            "payment_status": "confirmed",
            "events_log": [
                f"[PAYMENT] Sent ${price:.2f} USDC to {provider}",
                f"[PAYMENT] TX: {receipt['tx_hash']} on {receipt['chain']}",
            ],
        }
    except Exception as e:
        return {
            "payment_status": "failed",
            "marketplace_status": "failed",
            "events_log": [f"[PAYMENT] FAILED: {e}"],
        }


def payment_succeeded(state: MarketplaceState) -> str:
    """Conditional edge: route based on payment result."""
    if state.get("payment_status") == "confirmed":
        return "confirmed"
    return "failed"


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
    graph.add_node("execute_payment", execute_payment_node)
    graph.add_node("deliver_work", deliver_work_node)
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
        {"valid": "execute_payment", "invalid": "end_failed"},
    )

    # Conditional: payment result
    graph.add_conditional_edges(
        "execute_payment",
        payment_succeeded,
        {"confirmed": "deliver_work", "failed": "end_failed"},
    )

    # Terminal edges
    graph.add_edge("deliver_work", END)
    graph.add_edge("end_failed", END)

    return graph
