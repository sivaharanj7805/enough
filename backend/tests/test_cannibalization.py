"""Tests for cannibalization detection logic."""

import pytest
from app.services.cannibalization import (
    _severity_label,
    _position_proximity_factor,
    _traffic_split_factor,
)


class TestSeverityLabel:
    """Test severity label assignment from score."""

    def test_critical(self):
        assert _severity_label(0.75) == "critical"
        assert _severity_label(1.0) == "critical"

    def test_high(self):
        assert _severity_label(0.55) == "high"
        assert _severity_label(0.69) == "high"

    def test_medium(self):
        assert _severity_label(0.35) == "medium"
        assert _severity_label(0.49) == "medium"

    def test_low(self):
        assert _severity_label(0.1) == "low"
        assert _severity_label(0.29) == "low"

    def test_boundary_values(self):
        """Test exact boundary values."""
        assert _severity_label(0.3) == "low"   # <= 0.3
        assert _severity_label(0.5) == "medium" # <= 0.5
        assert _severity_label(0.7) == "high"   # <= 0.7
        assert _severity_label(0.0) == "low"


class TestPositionProximityFactor:
    """Test position proximity factor for severity scoring."""

    def test_both_top5(self):
        """Both in top 5 → 0.8 (high cannibalization risk)."""
        assert _position_proximity_factor(3.0, 4.0) == 0.8

    def test_both_top20(self):
        """Both in top 20 → 1.0 (competing directly)."""
        assert _position_proximity_factor(10.0, 15.0) == 1.0

    def test_one_top10_other_mid(self):
        """One top 10, other mid-range → 0.5."""
        assert _position_proximity_factor(8.0, 30.0) == 0.5

    def test_one_top10_other_far(self):
        """One top 10, other far away → 0.2."""
        assert _position_proximity_factor(5.0, 60.0) == 0.2

    def test_default_moderate(self):
        """Both far from top → 0.3."""
        assert _position_proximity_factor(30.0, 40.0) == 0.3


class TestTrafficSplitFactor:
    """Test traffic split factor from click distribution."""

    def test_even_split(self):
        """50/50 split → 1.0."""
        assert _traffic_split_factor(500, 500) == 1.0

    def test_moderate_split(self):
        """70/30 split → 0.7."""
        assert _traffic_split_factor(700, 300) == 0.7

    def test_skewed_split(self):
        """90/10 split → 0.3."""
        assert _traffic_split_factor(900, 100) == 0.3

    def test_extreme_split(self):
        """97/3 split → 0.1."""
        assert _traffic_split_factor(970, 30) == 0.1

    def test_zero_traffic(self):
        """No traffic → 0.5 default."""
        assert _traffic_split_factor(0, 0) == 0.5
