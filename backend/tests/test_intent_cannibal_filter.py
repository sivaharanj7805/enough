"""Tests for intent-aware cannibalization filtering."""

import pytest
from app.services.intent_cannibal_filter import (
    get_intent_multiplier,
    INTENT_OVERLAP,
    INTENT_MISMATCH_PENALTY,
    FilteredPair,
)


class TestIntentMultiplier:
    """Test intent overlap scoring."""

    def test_same_informational(self):
        assert get_intent_multiplier("informational", "informational") == 1.0

    def test_same_commercial(self):
        assert get_intent_multiplier("commercial", "commercial") == 1.0

    def test_same_transactional(self):
        assert get_intent_multiplier("transactional", "transactional") == 1.0

    def test_same_navigational(self):
        assert get_intent_multiplier("navigational", "navigational") == 1.0

    def test_informational_vs_commercial(self):
        """Compatible but not identical — should be 0.7."""
        assert get_intent_multiplier("informational", "commercial") == 0.7
        assert get_intent_multiplier("commercial", "informational") == 0.7

    def test_informational_vs_transactional(self):
        """Different intents — should be 0.5 (50% downgrade)."""
        assert get_intent_multiplier("informational", "transactional") == 0.5
        assert get_intent_multiplier("transactional", "informational") == 0.5

    def test_informational_vs_navigational(self):
        """Very different — should be 0.3."""
        assert get_intent_multiplier("informational", "navigational") == 0.3

    def test_unknown_intent_returns_1(self):
        """Unknown intent → no filtering (keep original score)."""
        assert get_intent_multiplier(None, "informational") == 1.0
        assert get_intent_multiplier("commercial", None) == 1.0
        assert get_intent_multiplier(None, None) == 1.0

    def test_case_insensitive(self):
        assert get_intent_multiplier("Informational", "COMMERCIAL") == 0.7

    def test_symmetric(self):
        """All pairs should give same result regardless of order."""
        intents = ["informational", "commercial", "transactional", "navigational"]
        for a in intents:
            for b in intents:
                assert get_intent_multiplier(a, b) == get_intent_multiplier(b, a)

    def test_all_pairs_covered(self):
        """Every intent combination should have a defined multiplier."""
        intents = ["informational", "commercial", "transactional", "navigational"]
        for a in intents:
            for b in intents:
                mult = get_intent_multiplier(a, b)
                assert 0.0 < mult <= 1.0


class TestIntentOverlapMatrix:
    """Test the overlap matrix is complete and consistent."""

    def test_matrix_is_symmetric(self):
        for (a, b), score in INTENT_OVERLAP.items():
            reverse = INTENT_OVERLAP.get((b, a))
            assert reverse is not None, f"Missing reverse pair ({b}, {a})"
            assert score == reverse, f"Asymmetric: ({a},{b})={score} vs ({b},{a})={reverse}"

    def test_all_same_intent_pairs_are_1(self):
        for intent in ["informational", "commercial", "transactional", "navigational"]:
            assert INTENT_OVERLAP[(intent, intent)] == 1.0

    def test_all_values_in_valid_range(self):
        for score in INTENT_OVERLAP.values():
            assert 0.0 < score <= 1.0


class TestFilteredPair:
    """Test the FilteredPair dataclass."""

    def test_downgraded_pair(self):
        from uuid import uuid4
        pair = FilteredPair(
            post_a_id=uuid4(),
            post_b_id=uuid4(),
            original_score=0.72,
            filtered_score=0.36,
            intent_a="informational",
            intent_b="transactional",
            multiplier=0.5,
            was_downgraded=True,
        )
        assert pair.was_downgraded
        assert pair.filtered_score < pair.original_score
        assert abs(pair.filtered_score - pair.original_score * pair.multiplier) < 0.001
