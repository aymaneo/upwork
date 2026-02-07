"""LangGraph state definition for the marketplace workflow."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class Bid(TypedDict):
    provider_name: str
    price_usdc: float
    reasoning: str


class PaymentReceipt(TypedDict):
    tx_hash: str
    from_addr: str
    to_addr: str
    amount_usdc: float
    chain: str


class MarketplaceState(TypedDict):
    job_description: str
    job_budget_usdc: float
    bids: Annotated[list[Bid], operator.add]
    selected_provider: str
    selected_price: float
    budget_valid: bool
    payment_receipt: PaymentReceipt
    payment_status: str  # "pending" | "confirmed" | "failed"
    escrow_status: str  # "pending" | "held" | "released" | "refunded"
    escrow_receipt: PaymentReceipt
    judge_verdict: str  # "approved" | "rejected"
    judge_reasoning: str
    work_result: str
    job_type: str  # "text" | "browser" | "shopping"
    marketplace_status: str  # "bidding" | "paying" | "delivering" | "judging" | "complete" | "failed"
    events_log: Annotated[list[str], operator.add]
