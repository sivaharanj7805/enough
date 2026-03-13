"""Tests for health scoring logic — 7-factor model, roles, ecosystem states, trends."""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.health_scoring import (
    _compute_trend,
    _ranking_score,
    _engagement_score,
    _freshness_score,
    _content_depth_score,
    _technical_seo_score,
    _assign_role,
    _assign_ecosystem_state,
)


class TestComputeTrend:
    """Test traffic trend computation (30d vs 30d comparison)."""

    def test_dead_very_low_traffic(self):
        """< 5 clicks in 60 days = dead."""
        trend, score = _compute_trend(recent_pv=2, prev_pv=2, total_60d_pv=4)
        assert trend == "dead"
        assert score == 0.0

    def test_dead_zero_everything(self):
        trend, score = _compute_trend(0, 0, 0)
        assert trend == "dead"

    def test_growing_significant_increase(self):
        """30%+ increase = growing."""
        trend, score = _compute_trend(recent_pv=130, prev_pv=100, total_60d_pv=230)
        assert trend == "growing"
        assert score >= 75.0

    def test_declining_significant_decrease(self):
        """>15% decrease = declining."""
        trend, score = _compute_trend(recent_pv=70, prev_pv=100, total_60d_pv=170)
        assert trend == "declining"
        assert score <= 25.0

    def test_stable_small_change(self):
        """Small change = stable."""
        trend, score = _compute_trend(recent_pv=105, prev_pv=100, total_60d_pv=205)
        assert trend == "stable"
        assert score == 50.0

    def test_growing_from_zero(self):
        """Previous was 0, now has traffic = growing."""
        trend, score = _compute_trend(recent_pv=50, prev_pv=0, total_60d_pv=50)
        assert trend == "growing"
        assert score == 100.0


class TestRankingScore:
    """Test ranking score normalization."""

    def test_position_1(self):
        assert _ranking_score(1.0) == 100.0

    def test_position_50_plus(self):
        assert _ranking_score(50.0) == 0.0
        assert _ranking_score(100.0) == 0.0

    def test_position_10(self):
        score = _ranking_score(10.0)
        assert 60 < score < 95  # Top 10 is still very strong

    def test_top_positions_worth_more(self):
        """Exponential decay — top positions are disproportionately valuable."""
        pos_3 = _ranking_score(3.0)
        pos_10 = _ranking_score(10.0)
        pos_20 = _ranking_score(20.0)
        assert pos_3 > pos_10 > pos_20


class TestEngagementScore:
    """Test engagement score from bounce rate + time on page."""

    def test_great_engagement(self):
        score = _engagement_score(bounce_rate=0.2, avg_time_seconds=180.0)
        assert score > 60  # 0.4 * 80 + 0.6 * 60 = 68

    def test_terrible_engagement(self):
        score = _engagement_score(bounce_rate=0.95, avg_time_seconds=5.0)
        assert score < 15

    def test_mixed_engagement(self):
        score = _engagement_score(bounce_rate=0.5, avg_time_seconds=60.0)
        assert 20 < score < 50


class TestFreshnessScore:
    """Test freshness scoring based on update age."""

    def test_updated_today(self):
        now = datetime.now(timezone.utc)
        assert _freshness_score(now, now) == 100.0

    def test_2_months_old(self):
        now = datetime.now(timezone.utc)
        two_months_ago = now - timedelta(days=60)
        assert _freshness_score(two_months_ago, now) == 80.0

    def test_4_months_old(self):
        now = datetime.now(timezone.utc)
        four_months_ago = now - timedelta(days=120)
        assert _freshness_score(four_months_ago, now) == 60.0

    def test_9_months_old(self):
        now = datetime.now(timezone.utc)
        nine_months_ago = now - timedelta(days=270)
        assert _freshness_score(nine_months_ago, now) == 40.0

    def test_2_years_old(self):
        now = datetime.now(timezone.utc)
        two_years_ago = now - timedelta(days=730)
        assert _freshness_score(two_years_ago, now) == 0.0

    def test_no_date(self):
        now = datetime.now(timezone.utc)
        assert _freshness_score(None, now) == 20.0


class TestContentDepthScore:
    """Test content depth scoring vs cluster average."""

    def test_very_thin(self):
        assert _content_depth_score(200, 1000) == 10.0

    def test_below_minimum(self):
        assert _content_depth_score(400, 1000) == 30.0

    def test_below_cluster_avg(self):
        score = _content_depth_score(600, 1000)
        assert 40 <= score <= 60

    def test_at_cluster_avg(self):
        score = _content_depth_score(1000, 1000)
        assert 55 <= score <= 65

    def test_above_cluster_avg(self):
        score = _content_depth_score(1400, 1000)
        assert score > 75

    def test_far_above_avg(self):
        score = _content_depth_score(2500, 1000)
        assert score >= 90


class TestTechnicalSEOScore:
    """Test technical SEO checklist scoring."""

    def test_all_checks_pass(self):
        score = _technical_seo_score(
            meta_description="A good description of the page content.",
            title="Perfect Title Length Here",  # 25 chars
            headings=[{"level": "h2", "text": "Section"}],
            has_outbound=True,
            has_inbound=True,
        )
        # Title is slightly short (25 < 30), so partial credit
        assert score >= 80

    def test_no_checks_pass(self):
        score = _technical_seo_score(
            meta_description=None,
            title="Hi",
            headings=None,
            has_outbound=False,
            has_inbound=False,
        )
        assert score <= 10

    def test_partial_pass(self):
        score = _technical_seo_score(
            meta_description="A good description of the page content.",
            title="Good Title for Blog Post About SEO Tips",
            headings=None,
            has_outbound=True,
            has_inbound=False,
        )
        assert 40 <= score <= 70


class TestAssignRole:
    """Test role assignment logic."""

    def test_dead_weight_low_composite(self):
        assert _assign_role(10, 0.1, 50, False) == "dead_weight"

    def test_dead_weight_no_traffic(self):
        assert _assign_role(60, 0.5, 0, False) == "dead_weight"

    def test_pillar_role(self):
        assert _assign_role(60, 0.35, 5000, False) == "pillar"

    def test_supporter_role(self):
        assert _assign_role(50, 0.15, 1000, False) == "supporter"

    def test_competitor_role(self):
        assert _assign_role(50, 0.2, 1000, True) == "competitor"

    def test_competitor_overrides_pillar(self):
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
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=10)
        metrics = self._make_metrics(
            ["supporter", "supporter"], ["growing", "stable"],
            [100, 50], [recent, recent],
        )
        state = _assign_ecosystem_state(metrics, 0, 2, 50.0, now, now - timedelta(days=30))
        assert state == "seedbed"

    def test_swamp_high_cannibalization(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 5, ["stable"] * 5, [100] * 5, [old] * 5,
        )
        state = _assign_ecosystem_state(metrics, 8, 5, 50.0, now, now - timedelta(days=30))
        assert state == "swamp"

    def test_desert_all_declining(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 4, ["declining"] * 4, [100] * 4, [old] * 4,
        )
        state = _assign_ecosystem_state(metrics, 0, 4, 50.0, now, now - timedelta(days=30))
        assert state == "desert"

    def test_desert_dead_posts(self):
        """All dead posts → desert."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["dead_weight"] * 4, ["dead"] * 4, [1] * 4, [old] * 4,
        )
        state = _assign_ecosystem_state(metrics, 0, 4, 10.0, now, now - timedelta(days=30))
        assert state == "desert"

    def test_forest_healthy(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["pillar", "supporter", "supporter", "supporter"],
            ["growing", "stable", "growing", "stable"],
            [5000, 1000, 800, 600], [old] * 4,
        )
        state = _assign_ecosystem_state(metrics, 0, 4, 60.0, now, now - timedelta(days=30))
        assert state == "forest"

    def test_meadow_default(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        metrics = self._make_metrics(
            ["supporter"] * 5, ["stable"] * 5, [200] * 5, [old] * 5,
        )
        state = _assign_ecosystem_state(metrics, 0, 5, 30.0, now, now - timedelta(days=30))
        assert state == "meadow"
