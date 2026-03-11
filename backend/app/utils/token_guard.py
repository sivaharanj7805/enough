"""Token guard — truncate content before sending to Claude/LLM APIs.

Prevents exceeding context windows and controls token costs by
truncating input content to a safe character limit before API calls.

Character-based approximation: 1 token ≈ 4 characters (conservative).
"""

import logging

logger = logging.getLogger(__name__)

# Default limits (characters) — conservative, based on ~4 chars/token
DEFAULT_CHAR_LIMIT = 80_000  # ~20k tokens
ORACLE_CHAR_LIMIT = 80_000  # Oracle analysis
DRAFT_CHAR_LIMIT = 120_000  # Draft generation (needs more context)
LABEL_CHAR_LIMIT = 2_000    # Cluster labeling


def truncate_for_api(
    content: str,
    max_chars: int = DEFAULT_CHAR_LIMIT,
    label: str = "content",
) -> str:
    """Truncate content to stay within token limits.

    Args:
        content: The text to truncate.
        max_chars: Maximum character count.
        label: Description for logging.

    Returns:
        Truncated string, with a note appended if truncation occurred.
    """
    if not content:
        return content

    if len(content) <= max_chars:
        return content

    truncated = content[:max_chars]
    logger.info(
        "Token guard: truncated %s from %d to %d chars (~%d tokens saved)",
        label,
        len(content),
        max_chars,
        (len(content) - max_chars) // 4,
    )
    return truncated + "\n\n[Content truncated for token limit]"


def truncate_body_texts(
    texts: list[str],
    max_per_text: int = 3000,
    max_total: int = DEFAULT_CHAR_LIMIT,
    label: str = "body_texts",
) -> list[str]:
    """Truncate a list of body texts, with per-item and total limits.

    Useful for consolidation where multiple post bodies are merged.
    """
    result = []
    total = 0
    for i, text in enumerate(texts):
        if total >= max_total:
            logger.info(
                "Token guard: skipped %d/%d remaining texts (total limit %d reached)",
                len(texts) - i, len(texts), max_total,
            )
            break
        remaining = max_total - total
        per_limit = min(max_per_text, remaining)
        truncated = truncate_for_api(text, max_chars=per_limit, label=f"{label}[{i}]")
        result.append(truncated)
        total += len(truncated)
    return result
