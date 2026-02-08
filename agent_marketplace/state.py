"""LangGraph state definition for the marketplace workflow."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class Bid(TypedDict):
    provider_name: str
    price_xpl: float
    reasoning: str


class PaymentReceipt(TypedDict):
    tx_hash: str
    from_addr: str
    to_addr: str
    amount_xpl: float
    chain: str


class MarketplaceState(TypedDict):
    job_description: str
    job_budget_xpl: float
    bids: Annotated[list[Bid], operator.add]
    selected_provider: str
    selected_price: float
    budget_valid: bool
    payment_receipt: PaymentReceipt
    payment_status: str  # "pending" | "confirmed" | "failed"
    escrow_id: str  # hex-encoded bytes32, e.g. "0xabc..."
    escrow_status: str  # "pending" | "held" | "released" | "refunded"
    escrow_receipt: PaymentReceipt
    judge_scores: dict  # {"completeness": 0.8, "relevance": 1.0, "quality": 0.7}
    judge_verdict: str  # "approved" | "rejected"
    judge_reasoning: str
    work_result: str
    job_type: str  # "text" | "browser" | "shopping"
    marketplace_status: str  # "bidding" | "paying" | "delivering" | "judging" | "complete" | "failed"
    events_log: Annotated[list[str], operator.add]
    # MCP discovery fields (set once during discover_providers)
    discovered_providers: list[dict]   # MCP + hardcoded provider descriptors
    mcp_provider_map: dict             # provider_name -> server_key (None for hardcoded)
    mcp_registry: dict                 # connection configs, passed through state
