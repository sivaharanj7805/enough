"""Tests for URL fluctuation detection."""

import pytest
from app.services.url_fluctuation import (
    URLFluctuationDetector,
    URLFluctuation,
    MIN_FLUCTUATIONS,
    WINDOW_DAYS,
    MIN_IMPRESSIONS,
)


class TestURLFluctuationDetector:
    """Test the detector class."""

    def test_instantiates(self):
        detector = URLFluctuationDetector()
        assert detector is not None

    def test_has_required_methods(self):
        detector = URLFluctuationDetector()
        assert hasattr(detector, 'record_daily_urls')
        assert hasattr(detector, 'detect_fluctuations')
        assert hasattr(detector, 'get_fluctuations')


class TestURLFluctuationDataclass:
    """Test the dataclass."""

    def test_creates_correctly(self):
        f = URLFluctuation(
            query="email marketing guide",
            urls_involved=["/email-guide", "/email-marketing-101", "/email-tips"],
            fluctuation_count=3,
            avg_position=8.5,
            total_impressions=450,
            severity="medium",
        )
        assert f.query == "email marketing guide"
        assert len(f.urls_involved) == 3
        assert f.fluctuation_count == 3
        assert f.severity == "medium"

    def test_critical_scenario(self):
        """5+ URLs or 1000+ impressions = critical."""
        f = URLFluctuation(
            query="best crm software",
            urls_involved=["/a", "/b", "/c", "/d", "/e"],
            fluctuation_count=5,
            avg_position=6.2,
            total_impressions=2500,
            severity="critical",
        )
        assert f.severity == "critical"
        assert f.fluctuation_count >= 5


class TestConstants:
    """Verify constants are sensible."""

    def test_min_fluctuations(self):
        assert MIN_FLUCTUATIONS == 3  # At least 3 URL changes to flag

    def test_window_days(self):
        assert WINDOW_DAYS == 30  # 30-day look-back

    def test_min_impressions(self):
        assert MIN_IMPRESSIONS == 20  # Ignore low-volume noise
