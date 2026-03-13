"""Tests for cannibalization detection logic (v2 — dual-signal)."""

import pytest
from app.services.cannibalization import CannibalizationDetector


class TestComputeSeverity:
    """Test severity computation from cosine similarity + shared query signals."""

    def test_critical_high_cosine_plus_shared(self):
        assert CannibalizationDetector._compute_severity(0.96, 3) == "critical"
        assert CannibalizationDetector._compute_severity(0.99, 1) == "critical"

    def test_high_cosine_only(self):
        assert CannibalizationDetector._compute_severity(0.91, 0) == "high"

    def test_high_moderate_cosine_plus_shared(self):
        assert CannibalizationDetector._compute_severity(0.87, 2) == "high"

    def test_medium_cosine_threshold(self):
        assert CannibalizationDetector._compute_severity(0.85, 0) == "medium"

    def test_medium_many_shared_queries(self):
        assert CannibalizationDetector._compute_severity(None, 5) == "medium"
        assert CannibalizationDetector._compute_severity(0.5, 3) == "medium"

    def test_low_few_shared_only(self):
        assert CannibalizationDetector._compute_severity(None, 1) == "low"
        assert CannibalizationDetector._compute_severity(None, 2) == "low"

    def test_low_no_cosine_few_shared(self):
        assert CannibalizationDetector._compute_severity(0.5, 1) == "low"


class TestComputeOverlapScore:
    """Test combined overlap score calculation."""

    def test_cosine_only(self):
        score = CannibalizationDetector._compute_overlap_score(0.90, 0, set(), set())
        assert score == 0.90

    def test_query_overlap_only(self):
        qa = {"seo tips", "seo guide", "seo basics"}
        qb = {"seo tips", "seo guide", "content marketing"}
        score = CannibalizationDetector._compute_overlap_score(None, 2, qa, qb)
        assert 0.0 < score < 1.0

    def test_both_signals(self):
        qa = {"keyword a", "keyword b"}
        qb = {"keyword a", "keyword c"}
        score = CannibalizationDetector._compute_overlap_score(0.90, 1, qa, qb)
        # Weighted: 0.7 * 0.90 + 0.3 * jaccard
        assert score > 0.60

    def test_no_signals(self):
        score = CannibalizationDetector._compute_overlap_score(None, 0, set(), set())
        assert score == 0.0

    def test_perfect_overlap(self):
        qa = {"seo", "content"}
        qb = {"seo", "content"}
        score = CannibalizationDetector._compute_overlap_score(0.99, 2, qa, qb)
        assert score > 0.95


class TestDetectorInit:
    """Test detector initialization."""

    def test_detector_instantiates(self):
        detector = CannibalizationDetector()
        assert detector is not None

    def test_thresholds_defined(self):
        from app.services.cannibalization import (
            COSINE_THRESHOLD_FLAG,
            COSINE_THRESHOLD_HIGH,
            COSINE_THRESHOLD_CRITICAL,
        )
        assert COSINE_THRESHOLD_FLAG == 0.85
        assert COSINE_THRESHOLD_HIGH == 0.90
        assert COSINE_THRESHOLD_CRITICAL == 0.95
