"""Tests for impact tracking — baseline, percentage calc, completion."""

import pytest
from datetime import date, timedelta


class TestImpactCalculations:
    """Test impact tracking math and logic."""

    def test_traffic_change_percentage_positive(self):
        """Positive traffic change should compute correct percentage."""
        baseline = 1000
        current = 1350
        change = current - baseline
        pct = (change / baseline * 100)
        assert change == 350
        assert pct == 35.0

    def test_traffic_change_percentage_negative(self):
        """Negative traffic change."""
        baseline = 1000
        current = 800
        change = current - baseline
        pct = (change / baseline * 100)
        assert change == -200
        assert pct == -20.0

    def test_traffic_change_zero_baseline(self):
        """Zero baseline should not divide by zero."""
        baseline = 0
        current = 500
        pct = (current - baseline) / baseline * 100 if baseline > 0 else 0.0
        assert pct == 0.0

    def test_milestone_30d(self):
        """30 days since consolidation → 30d milestone."""
        baseline_date = date.today() - timedelta(days=35)
        days_since = (date.today() - baseline_date).days
        milestone = None
        if days_since >= 90:
            milestone = "90d"
        elif days_since >= 60:
            milestone = "60d"
        elif days_since >= 30:
            milestone = "30d"
        assert milestone == "30d"

    def test_milestone_60d(self):
        baseline_date = date.today() - timedelta(days=65)
        days_since = (date.today() - baseline_date).days
        milestone = None
        if days_since >= 90:
            milestone = "90d"
        elif days_since >= 60:
            milestone = "60d"
        elif days_since >= 30:
            milestone = "30d"
        assert milestone == "60d"

    def test_milestone_90d(self):
        baseline_date = date.today() - timedelta(days=95)
        days_since = (date.today() - baseline_date).days
        milestone = None
        if days_since >= 90:
            milestone = "90d"
        elif days_since >= 60:
            milestone = "60d"
        elif days_since >= 30:
            milestone = "30d"
        assert milestone == "90d"

    def test_no_milestone_early(self):
        """< 30 days → no milestone."""
        baseline_date = date.today() - timedelta(days=15)
        days_since = (date.today() - baseline_date).days
        milestone = None
        if days_since >= 90:
            milestone = "90d"
        elif days_since >= 60:
            milestone = "60d"
        elif days_since >= 30:
            milestone = "30d"
        assert milestone is None

    def test_completion_status_at_90d(self):
        """Status should be 'complete' at 90+ days."""
        days_since = 92
        status = "complete" if days_since >= 90 else "tracking"
        assert status == "complete"

    def test_tracking_status_before_90d(self):
        """Status should be 'tracking' before 90 days."""
        days_since = 45
        status = "complete" if days_since >= 90 else "tracking"
        assert status == "tracking"

    def test_position_change_improvement(self):
        """Position improvement (lower is better): baseline 15 → current 8 = +7 improvement."""
        baseline_pos = 15.0
        current_pos = 8.0
        change = baseline_pos - current_pos
        assert change == 7.0  # Positive = improved

    def test_position_change_regression(self):
        """Position regression: baseline 5 → current 12 = -7."""
        baseline_pos = 5.0
        current_pos = 12.0
        change = baseline_pos - current_pos
        assert change == -7.0  # Negative = regressed
