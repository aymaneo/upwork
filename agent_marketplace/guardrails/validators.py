"""Budget validation guardrails using guardrails-ai."""

from __future__ import annotations

from guardrails import Guard
from guardrails.errors import ValidationError
from guardrails.validators import (
    FailResult,
    PassResult,
    ValidationResult,
    Validator,
    register_validator,
)

from agent_marketplace.state import MarketplaceState


@register_validator(name="budget-check", data_type="string")
class BudgetValidator(Validator):
    """Validates that a bid price does not exceed the job budget."""

    def __init__(self, budget: float, **kwargs):
        super().__init__(budget=budget, **kwargs)
        self.budget = budget

    def validate(self, value, metadata: dict | None = None) -> ValidationResult:
        price = float(value)
        if price > self.budget:
            return FailResult(
                error_message=(
                    f"Bid ${price:.4f} exceeds budget ${self.budget:.4f}"
                ),
            )
        return PassResult()


def validate_budget_node(state: MarketplaceState) -> dict:
    """LangGraph node: validate bid price against budget using guardrails-ai."""
    budget = state["job_budget_usdc"]
    price = state["selected_price"]
    provider = state["selected_provider"]

    guard = Guard().use(BudgetValidator(budget=budget), on="output")

    try:
        guard.validate(str(price))
        return {
            "budget_valid": True,
            "events_log": [
                f"[GUARDRAIL] APPROVED: {provider} bid ${price:.4f} "
                f"is within budget ${budget:.4f} XPL",
            ],
        }
    except ValidationError:
        return {
            "budget_valid": False,
            "marketplace_status": "failed",
            "events_log": [
                f"[GUARDRAIL] REJECTED: {provider} bid ${price:.4f} "
                f"exceeds budget ${budget:.4f} XPL",
            ],
        }


def budget_is_valid(state: MarketplaceState) -> str:
    """Conditional edge: route based on budget validation result."""
    if state.get("budget_valid"):
        return "valid"
    return "invalid"
