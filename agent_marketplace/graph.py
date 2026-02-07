"""LangGraph workflow: wires all agent nodes and conditional edges."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from agent_marketplace.agents.client import (
    judge_work_node,
    post_job_node,
    select_provider_node,
)
from agent_marketplace.agents.provider import (
    _bid_prompt,
    _parse_bid,
    close_bidding_node,
    deliver_work_node,
)
from agent_marketplace.config import PROVIDER_WALLET_ADDRESS
from agent_marketplace.guardrails.validators import (
    budget_is_valid,
    validate_budget_node,
)
from agent_marketplace.payments.plasma import PlasmaEscrowProvider
from agent_marketplace.state import Bid, MarketplaceState

logger = logging.getLogger(__name__)

# Shared payment provider instance (set at runtime via set_payment_provider)
_payment_provider: PlasmaEscrowProvider | None = None


def set_payment_provider(provider: PlasmaEscrowProvider) -> None:
    global _payment_provider
    _payment_provider = provider


# ---------------------------------------------------------------------------
# Discovery node
# ---------------------------------------------------------------------------


def discover_providers_node(state: MarketplaceState) -> dict:
    """Discover MCP + hardcoded providers, filter by job_type capability."""
    from agent_marketplace.mcp import run_async
    from agent_marketplace.mcp.registry import discover_all_providers

    registry = state.get("mcp_registry", {})
    job_type = state.get("job_type", "text")

    providers, warnings = run_async(discover_all_providers(registry))

    # Filter by capability
    compatible = [
        p for p in providers if job_type in p.get("capabilities", [])
    ]
    if not compatible:
        # Fallback: use all providers
        compatible = providers

    # Build provider_name -> server_key map
    provider_map = {p["name"]: p.get("server_key") for p in compatible}

    names = [p["name"] for p in compatible]
    events = list(warnings)  # surface MCP warnings
    events.append(
        f"[DISCOVERY] Found {len(compatible)} providers: {', '.join(names)}"
    )
    return {
        "discovered_providers": compatible,
        "mcp_provider_map": provider_map,
        "events_log": events,
    }


# ---------------------------------------------------------------------------
# Dynamic fan-out: one bid per provider
# ---------------------------------------------------------------------------


def fan_out_bids(state: MarketplaceState) -> list[Send]:
    """Conditional edge that returns a list of Send() — one per provider."""
    providers = state.get("discovered_providers", [])
    sends = []
    for provider in providers:
        sends.append(
            Send(
                "bid_provider",
                {
                    **state,
                    "_current_provider": provider,
                },
            )
        )
    return sends


def bid_provider_node(state: MarketplaceState) -> dict:
    """Unified bid node — handles both MCP and hardcoded providers."""
    provider_info: dict[str, Any] = state["_current_provider"]
    name = provider_info["name"]
    server_key = provider_info.get("server_key")
    source = provider_info.get("source", "local")

    desc = state["job_description"]
    budget = state["job_budget_xpl"]
    job_type = state.get("job_type", "text")

    if server_key is not None and source == "mcp":
        # MCP bid
        registry = state.get("mcp_registry", {})
        from agent_marketplace.mcp import run_async
        from agent_marketplace.mcp.client import MarketplaceMCPClient

        async def _mcp_bid() -> dict[str, Any]:
            async with MarketplaceMCPClient(registry) as client:
                return await client.call_bid(server_key, desc, budget, job_type)

        try:
            result = run_async(_mcp_bid())
            price = float(result.get("price_xpl", budget * 0.5))
            reasoning = result.get("reasoning", "")
            # Clamp
            price = min(price, round(budget * 0.9, 6))
        except Exception as exc:
            logger.warning("MCP bid from '%s' failed: %s", name, exc)
            price = round(budget * 0.5, 4)
            reasoning = f"MCP bid failed ({exc}), using fallback price"
    else:
        # Hardcoded (local) bid
        agent = provider_info.get("agent")
        hint = provider_info.get("persona_hint", "Bid competitively.")
        if agent is None:
            from agent_marketplace.agents.base import BaseAgent
            agent = BaseAgent(persona=f"You are '{name}', a marketplace provider.")

        prompt = _bid_prompt(desc, budget, hint)
        response = agent.think(prompt)
        price, reasoning = _parse_bid(response, budget)

    bid: Bid = {
        "provider_name": name,
        "price_xpl": price,
        "reasoning": reasoning,
    }

    tag = name.upper().replace(" ", " ")
    return {
        "bids": [bid],
        "events_log": [
            f"[{tag}] Bid: {price} XPL",
            f"[{tag}] {reasoning}",
        ],
    }


# ---------------------------------------------------------------------------
# Escrow nodes
# ---------------------------------------------------------------------------


def escrow_hold_node(state: MarketplaceState) -> dict:
    """Deposit funds into the on-chain escrow contract."""
    provider = state["selected_provider"]
    price = state["selected_price"]

    try:
        escrow_id = _payment_provider.generate_escrow_id(
            state["job_description"], PROVIDER_WALLET_ADDRESS
        )
        receipt = _payment_provider.deposit(
            escrow_id, PROVIDER_WALLET_ADDRESS, price
        )
        escrow_id_hex = "0x" + escrow_id.hex()
        return {
            "escrow_id": escrow_id_hex,
            "escrow_status": "held",
            "escrow_receipt": receipt,
            "marketplace_status": "delivering",
            "events_log": [
                f"[ESCROW] Deposited {price:.4f} XPL into contract for {provider}",
                f"[ESCROW] Escrow ID: {escrow_id_hex[:18]}...",
                f"[ESCROW] Deposit TX: {receipt['tx_hash']} on {receipt['chain']}",
            ],
        }
    except Exception as e:
        return {
            "escrow_status": "failed",
            "marketplace_status": "failed",
            "events_log": [f"[ESCROW] Deposit FAILED: {e}"],
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
    escrow_id_hex = state["escrow_id"]
    escrow_id = bytes.fromhex(escrow_id_hex[2:])

    try:
        receipt = _payment_provider.release(escrow_id)
        return {
            "escrow_status": "released",
            "payment_receipt": receipt,
            "payment_status": "confirmed",
            "marketplace_status": "complete",
            "events_log": [
                f"[ESCROW] Released {price:.4f} XPL to {provider}",
                f"[ESCROW] Release TX: {receipt['tx_hash']} on {receipt['chain']}",
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
    escrow_id_hex = state["escrow_id"]
    escrow_id = bytes.fromhex(escrow_id_hex[2:])

    try:
        receipt = _payment_provider.refund(escrow_id)
        return {
            "escrow_status": "refunded",
            "payment_receipt": receipt,
            "marketplace_status": "failed",
            "events_log": [
                f"[ESCROW] Refunded {price:.4f} XPL to client",
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


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Construct the marketplace LangGraph workflow.

    Flow:
        post_job → discover_providers → [fan_out_bids via Send()]
            → bid_provider (×N) → close_bidding → select_provider
            → validate_budget → escrow_hold → deliver_work → judge_work
            → escrow_release | escrow_refund
    """
    graph = StateGraph(MarketplaceState)

    # Add nodes
    graph.add_node("post_job", post_job_node)
    graph.add_node("discover_providers", discover_providers_node)
    graph.add_node("bid_provider", bid_provider_node)
    graph.add_node("close_bidding", close_bidding_node)
    graph.add_node("select_provider", select_provider_node)
    graph.add_node("validate_budget", validate_budget_node)
    graph.add_node("escrow_hold", escrow_hold_node)
    graph.add_node("deliver_work", deliver_work_node)
    graph.add_node("judge_work", judge_work_node)
    graph.add_node("escrow_release", escrow_release_node)
    graph.add_node("escrow_refund", escrow_refund_node)
    graph.add_node("end_failed", end_failed_node)

    # Entry
    graph.set_entry_point("post_job")
    graph.add_edge("post_job", "discover_providers")

    # Dynamic fan-out: discover_providers → Send("bid_provider", ...) × N
    graph.add_conditional_edges("discover_providers", fan_out_bids)

    # All bid_provider instances converge at close_bidding
    graph.add_edge("bid_provider", "close_bidding")
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
