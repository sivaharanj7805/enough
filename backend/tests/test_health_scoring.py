"""Tests for health scoring logic — roles, ecosystem states, trend computation."""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.health_scoring import (
    _compute_trend,
    _assign_role,
    _assign_ecosystem_state,
)


class TestComputeTrend:
    """Test traffic trend computation."""

    def test_too_few_data_points(self):
        """< 7 days should return stable/0.5."""
        data = [{"date": "2024-01-01", "pv": 100}] * 3
        trend, score = _compute_trend(data)
        assert trend == "stable"
        assert score == 0.5

    def test_growing_trend(self):
        """Steadily increasing traffic should be 'growing'."""
        data = [{"date": f"2024-01-{i+1:02d}", "pv": 100 + i * 20} for i in range(30)]
        trend, score = _compute_trend(data)
        assert trend == "growing"
        assert score == 1.0

    def test_declining_trend(self):
        """Steadily decreasing traffic should be 'declining'."""
        data = [{"date": f"2024-01-{i+1:02d}", "pv": 1000 - i * 30} for i in range(30)]
        trend, score = _compute_trend(data)
        assert trend == "declining"
        assert score == 0.0

    def test_stable_trend(self):
        """Flat traffic should be 'stable'."""
        data = [{"date": f"2024-01-{i+1:02d}", "pv": 100} for i in range(30)]
        trend, score = _compute_trend(data)
        assert trend == "stable"
        assert score == 0.5

    def test_empty_data(self):
        """Empty data should return stable."""
        trend, score = _compute_trend([])
        assert trend == "stable"
        assert score == 0.5


class TestAssignRole:
    """Test role assignment logic."""

    def test_dead_weight_low_composite(self):
        """Very low composite score = dead_weight."""
        assert _assign_role(10, 0.1, 50, False) == "dead_weight"

    def test_dead_weight_no_traffic(self):
        """Zero pageviews = dead_weight regardless of composite."""
        assert _assign_role(60, 0.5, 0, False) == "dead_weight"

    def test_pillar_role(self):
        """High traffic contribution + high composite = pillar."""
        assert _assign_role(60, 0.35, 5000, False) == "pillar"

    def test_supporter_role(self):
        """High composite but lower traffic contribution = supporter."""
        assert _assign_role(50, 0.15, 1000, False) == "supporter"

    def test_competitor_role(self):
        """Cannibalizing post = competitor."""
        assert _assign_role(50, 0.2, 1000, True) == "competitor"

    def test_competitor_overrides_pillar(self):
        """Cannibalization flag overrides pillar."""
        assert _assign_role(80, 0.5, 5000, True) == "competitor"


class TestAssignEcosystemState:
    """Test ecosystem state assignment."""

    def _make_metrics(self, roles, trends, traffics, publish_dates=None):
        now = datetime.now(timezone.utc)
        result = []
        for i, (role, trend, traffic) in enumerate(zip(roles, trends, traffics)):
            pd = publish_dates[i] if publish_dates else now - timedelta(days=90)
            result.append({
                "role": role,
                "trend": trend,
                "traffic": traffic,
                "publish_date": pd,
                "composite": 50.0,
            })
        return result

    def test_seedbed_recent_small(self):
        """Small cluster with recent posts → seedbed."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=10)
        metrics = self._make_metrics(
            ["supporter", "supporter"],
            ["growing", "stable"],
            [100, 50],
            [recent, recent],
        )
        state = _assign_ecosystem_state(metrics, 0, 2, 50.0, now, now - timedelta(days=30))
        assert state == "seedbed"

    def test_swamp_high_cannibalization(self):
        """High cannibalization rate → swamp."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 5,
            ["stable"] * 5,
            [100] * 5,
            [old] * 5,
        )
        # 8 cannibalization pairs out of 10 possible = 80%
        state = _assign_ecosystem_state(metrics, 8, 5, 50.0, now, now - timedelta(days=30))
        assert state == "swamp"

    def test_swamp_many_posts_no_pillar(self):
        """Large cluster without a pillar → swamp."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 10,
            ["stable"] * 10,
            [100] * 10,
            [old] * 10,
        )
        state = _assign_ecosystem_state(metrics, 0, 10, 50.0, now, now - timedelta(days=30))
        assert state == "swamp"

    def test_desert_all_declining(self):
        """All posts declining → desert."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 4,
            ["declining"] * 4,
            [100] * 4,
            [old] * 4,
        )
        state = _assign_ecosystem_state(metrics, 0, 4, 50.0, now, now - timedelta(days=30))
        assert state == "desert"

    def test_desert_very_low_traffic(self):
        """Very low average traffic → desert."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 4,
            ["stable"] * 4,
            [2] * 4,
            [old] * 4,
        )
        state = _assign_ecosystem_state(metrics, 0, 4, 50.0, now, now - timedelta(days=30))
        assert state == "desert"

    def test_forest_healthy_with_pillar(self):
        """Healthy cluster with pillar, low cannibalization → forest."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["pillar", "supporter", "supporter", "supporter"],
            ["growing", "stable", "growing", "stable"],
            [5000, 1000, 800, 600],
            [old] * 4,
        )
        state = _assign_ecosystem_state(metrics, 0, 4, 60.0, now, now - timedelta(days=30))
        assert state == "forest"

    def test_meadow_default(self):
        """Medium cluster that doesn't match other states → meadow."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 5,
            ["stable"] * 5,
            [200] * 5,
            [old] * 5,
        )
        state = _assign_ecosystem_state(metrics, 0, 5, 30.0, now, now - timedelta(days=30))
        assert state == "meadow"
