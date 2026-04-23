"""Budget estimation and enforcement for LedgerAgent."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from .models import BudgetState

DEFAULT_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "evals-anthropic/claude-sonnet-4-6": (0.003, 0.015),
    "evals-openai/gpt-5.4": (0.005, 0.015),
}


class BudgetExceededError(RuntimeError):
    """Raised when the next model call would exceed the configured budget."""


@dataclass(frozen=True)
class BudgetConfig:
    """Static budget and pricing configuration."""

    max_budget_usd: float = 0.25
    input_cost_per_1k: float = 0.003
    output_cost_per_1k: float = 0.015
    chars_per_token: int = 4


class BudgetManager:
    """Tracks estimated token and cost usage across the run."""

    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self.state = BudgetState(max_budget_usd=config.max_budget_usd)

    @classmethod
    def for_model(cls, model_name: str, *, max_budget_usd: float) -> BudgetManager:
        input_cost, output_cost = DEFAULT_MODEL_PRICING.get(
            model_name,
            DEFAULT_MODEL_PRICING["evals-anthropic/claude-sonnet-4-6"],
        )
        return cls(
            BudgetConfig(
                max_budget_usd=max_budget_usd,
                input_cost_per_1k=input_cost,
                output_cost_per_1k=output_cost,
            )
        )

    def estimate_tokens(self, payload: Any) -> int:
        text = self._normalize_payload(payload)
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self.config.chars_per_token))

    def reserve_model_call(
        self,
        *,
        prompt_payload: Any,
        max_output_tokens: int,
    ) -> None:
        input_tokens = self.estimate_tokens(prompt_payload)
        projected_cost = self._cost_for_tokens(input_tokens, max_output_tokens)
        if self.state.spent_usd + projected_cost > self.config.max_budget_usd:
            self.state.blocked = True
            self.state.blocked_reason = (
                f"Budget cap would be exceeded by the next model call "
                f"({self.state.spent_usd + projected_cost:.4f} > {self.config.max_budget_usd:.4f})."
            )
            raise BudgetExceededError(self.state.blocked_reason)

    def record_model_call(
        self,
        *,
        prompt_payload: Any,
        response_payload: Any,
    ) -> None:
        input_tokens = self.estimate_tokens(prompt_payload)
        output_tokens = self.estimate_tokens(response_payload)
        self.state.estimated_input_tokens += input_tokens
        self.state.estimated_output_tokens += output_tokens
        self.state.spent_usd += self._cost_for_tokens(input_tokens, output_tokens)

    def _cost_for_tokens(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1000) * self.config.input_cost_per_1k
            + (output_tokens / 1000) * self.config.output_cost_per_1k
        )

    def _normalize_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, sort_keys=True, default=str)
