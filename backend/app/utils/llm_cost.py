"""LLM cost logging utility — fire-and-forget cost tracking."""

import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (USD) — update when pricing changes.
# Exact model ID → (input_cost_per_1M, output_cost_per_1M)
MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-3-5-haiku-20241022": (0.25, 1.25),
    "text-embedding-3-small": (0.02, 0.0),
}

# Prefix fallbacks for future model versions (e.g., claude-sonnet-4-20260101).
# Each prefix maps to the rates of the model family it belongs to.
_PREFIX_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4": (3.0, 15.0),
    "claude-3-5-haiku": (0.25, 1.25),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Compute estimated USD cost from token counts."""
    rates = MODEL_RATES.get(model)
    if not rates:
        for prefix, val in _PREFIX_RATES.items():
            if model.startswith(prefix):
                rates = val
                break
    if not rates:
        return None
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


async def log_llm_usage(
    db: asyncpg.Connection,
    *,
    site_id: UUID | None,
    service: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> None:
    """Log an LLM API call's token usage. Fire-and-forget: logs errors but never raises."""
    try:
        cost = _estimate_cost(model, input_tokens, output_tokens)
        await db.execute(
            """INSERT INTO llm_cost_log
                   (site_id, service, model, input_tokens, output_tokens, estimated_cost_usd)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            site_id, service, model, input_tokens, output_tokens, cost,
        )
    except Exception:
        logger.warning(
            "Failed to log LLM cost: service=%s model=%s tokens=%d/%d",
            service, model, input_tokens, output_tokens,
            exc_info=True,
        )
