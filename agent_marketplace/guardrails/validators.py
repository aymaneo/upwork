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
                    f"Bid {price:.4f} XPL exceeds budget {self.budget:.4f} XPL"
                ),
            )
        return PassResult()


_RUBRIC_KEYS = ("completeness", "relevance", "quality")


@register_validator(name="rubric-check", data_type="string")
class RubricValidator(Validator):
    """Validates that judge output is a well-formed rubric JSON."""

    def validate(self, value, metadata: dict | None = None) -> ValidationResult:
        import json as _json

        try:
            data = _json.loads(value)
        except (ValueError, TypeError):
            return FailResult(error_message="Invalid JSON")

        for key in (*_RUBRIC_KEYS, "reasoning"):
            if key not in data:
                return FailResult(error_message=f"Missing required key: {key}")

        for key in _RUBRIC_KEYS:
            score = data[key]
            if not isinstance(score, (int, float)):
                return FailResult(error_message=f"{key} must be a number, got {type(score).__name__}")
            if not (0.0 <= float(score) <= 1.0):
                return FailResult(error_message=f"{key} must be between 0.0 and 1.0, got {score}")

        if not isinstance(data["reasoning"], str) or not data["reasoning"].strip():
            return FailResult(error_message="reasoning must be a non-empty string")

        return PassResult()


def validate_budget_node(state: MarketplaceState) -> dict:
    """LangGraph node: validate bid price against budget using guardrails-ai."""
    budget = state["job_budget_xpl"]
    price = state["selected_price"]
    provider = state["selected_provider"]

    guard = Guard().use(BudgetValidator(budget=budget), on="output")

    try:
        guard.validate(str(price))
        return {
            "budget_valid": True,
            "events_log": [
                f"[GUARDRAIL] APPROVED: {provider} bid {price:.4f} XPL "
                f"is within budget {budget:.4f} XPL",
            ],
        }
    except ValidationError:
        return {
            "budget_valid": False,
            "marketplace_status": "failed",
            "events_log": [
                f"[GUARDRAIL] REJECTED: {provider} bid {price:.4f} XPL "
                f"exceeds budget {budget:.4f} XPL",
            ],
        }


def budget_is_valid(state: MarketplaceState) -> str:
    """Conditional edge: route based on budget validation result."""
    if state.get("budget_valid"):
        return "valid"
    return "invalid"
