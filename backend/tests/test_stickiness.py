"""Tests for Stickiness Features — 5 features that transform
from "interesting tool" to "can't cancel."

1. Historical Tracking + Change Detection
2. Smart Alerts
3. Impact Tracking
4. Content Briefs
5. Keyword Opportunity Scoring
"""

import pytest
from uuid import uuid4


# ═══════════════════════════════════════════════
# 3. Impact Tracking
# ═══════════════════════════════════════════════


class TestImpactTracking:
    """Test impact tracking logic."""

    def test_tracker_instantiates(self):
        from app.services.impact_tracking import ImpactTracker
        tracker = ImpactTracker()
        assert tracker is not None

    def test_has_required_methods(self):
        from app.services.impact_tracking import ImpactTracker
        tracker = ImpactTracker()
        assert hasattr(tracker, 'record_completion')
        assert hasattr(tracker, 'update_impacts')
        assert hasattr(tracker, 'get_monthly_report')


# ═══════════════════════════════════════════════
# 4. Content Briefs
# ═══════════════════════════════════════════════


class TestContentBriefs:
    """Test content brief generation logic."""

    def test_brief_generator_instantiates(self):
        from app.services.content_briefs import ContentBriefGenerator
        gen = ContentBriefGenerator()
        assert gen is not None

    def test_has_required_methods(self):
        from app.services.content_briefs import ContentBriefGenerator
        gen = ContentBriefGenerator()
        assert hasattr(gen, 'generate_brief')
        assert hasattr(gen, 'generate_briefs_for_gaps')


# ═══════════════════════════════════════════════
# Import verification
# ═══════════════════════════════════════════════


class TestStickynessImports:
    """Verify all stickiness services import cleanly."""

    def test_import_impact_tracking(self):
        from app.services.impact_tracking import ImpactTracker
        assert ImpactTracker is not None

    def test_import_content_briefs(self):
        from app.services.content_briefs import ContentBriefGenerator
        assert ContentBriefGenerator is not None
