"""Tests for Intelligence Layer V2 — 8 new features.

1. Internal PageRank
2. Topical Authority Scoring
3. Search Intent Classification
4. Content Gap Analysis
5. Weighted Embedding Strategy
6. Content Velocity Tracking
7. SERP Feature Opportunity Detection
8. Readability Scoring
"""

import pytest

# ═══════════════════════════════════════════════
# 8. Readability Scoring (no external deps)
# ═══════════════════════════════════════════════


class TestReadability:
    """Test readability scoring functions."""

    def test_flesch_reading_ease_simple(self):
        from app.services.readability import compute_flesch_reading_ease
        # Simple text should score high (easy to read)
        text = "The cat sat on the mat. The dog ran in the park. It was a nice day."
        score = compute_flesch_reading_ease(text)
        assert score > 70.0  # Should be easy

    def test_flesch_reading_ease_complex(self):
        from app.services.readability import compute_flesch_reading_ease
        # Complex academic text should score lower
        text = (
            "The epistemological implications of phenomenological hermeneutics "
            "necessitate a comprehensive reconsideration of methodological "
            "presuppositions underlying contemporary philosophical investigations "
            "into consciousness and intentionality."
        )
        score = compute_flesch_reading_ease(text)
        assert score < 40.0  # Should be difficult

    def test_flesch_reading_ease_empty(self):
        from app.services.readability import compute_flesch_reading_ease
        assert compute_flesch_reading_ease("") == 0.0

    def test_grade_level_simple(self):
        from app.services.readability import compute_grade_level
        text = "The cat sat on the mat. The dog ran in the park."
        grade = compute_grade_level(text)
        assert grade < 5.0  # Should be elementary level

    def test_grade_level_complex(self):
        from app.services.readability import compute_grade_level
        text = (
            "The epistemological implications necessitate comprehensive "
            "reconsideration of methodological presuppositions."
        )
        grade = compute_grade_level(text)
        assert grade > 10.0  # Should be high school+

    def test_syllable_counting(self):
        from app.services.readability import _syllables_in_word
        assert _syllables_in_word("cat") == 1
        assert _syllables_in_word("hello") == 2
        assert _syllables_in_word("beautiful") == 3
        assert _syllables_in_word("a") == 1

    def test_sentence_counting(self):
        from app.services.readability import _count_sentences
        assert _count_sentences("Hello. World.") == 2
        assert _count_sentences("Hello! World? Yes.") == 3
        assert _count_sentences("No punctuation here") == 1

    def test_word_counting(self):
        from app.services.readability import _count_words
        assert _count_words("hello world") == 2
        assert _count_words("one two three four") == 4
        assert _count_words("") == 0


# ═══════════════════════════════════════════════
# 3. Search Intent Classification (query patterns)
# ═══════════════════════════════════════════════


class TestIntentClassification:
    """Test rule-based query intent classification."""

    def test_informational_how_to(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("how to tie a tie") == "informational"

    def test_informational_what_is(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("what is SEO") == "informational"

    def test_transactional_buy(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("buy running shoes") == "transactional"

    def test_transactional_pricing(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("pricing plans CRM software") == "transactional"

    def test_commercial_best(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("best CRM software 2024") == "commercial"

    def test_commercial_vs(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("hubspot vs salesforce") == "commercial"

    def test_commercial_review(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("ahrefs review") == "commercial"

    def test_navigational_login(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("gmail login") == "navigational"

    def test_navigational_website(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("openai official website") == "navigational"

    def test_default_informational(self):
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("content marketing") == "informational"

    def test_transactional_beats_informational(self):
        """Transactional patterns checked first — 'buy' overrides 'guide'."""
        from app.services.intent_classifier import classify_query_intent
        assert classify_query_intent("buy guide book") == "transactional"


# ═══════════════════════════════════════════════
# 1. Internal PageRank
# ═══════════════════════════════════════════════


class TestInternalPageRank:
    """Test PageRank computation."""

    def test_compute_pagerank_simple(self):
        from app.services.pagerank import InternalPageRank
        from uuid import uuid4

        a, b, c = uuid4(), uuid4(), uuid4()
        edges = [(a, b), (b, c), (c, a)]  # Cycle
        nodes = {a, b, c}

        pr = InternalPageRank._compute_pagerank(edges, nodes)

        # All nodes in a cycle should have roughly equal PageRank
        assert abs(pr[a] - pr[b]) < 0.01
        assert abs(pr[b] - pr[c]) < 0.01
        assert abs(sum(pr.values()) - 1.0) < 1e-6

    def test_compute_pagerank_hub_and_spoke(self):
        from app.services.pagerank import InternalPageRank
        from uuid import uuid4

        hub = uuid4()
        spokes = [uuid4() for _ in range(5)]
        nodes = {hub} | set(spokes)
        edges = [(s, hub) for s in spokes]  # All point to hub

        pr = InternalPageRank._compute_pagerank(edges, nodes)

        # Hub should have highest PageRank
        assert pr[hub] > max(pr[s] for s in spokes)
        assert abs(sum(pr.values()) - 1.0) < 1e-6

    def test_compute_pagerank_isolated_nodes(self):
        from app.services.pagerank import InternalPageRank
        from uuid import uuid4

        a, b, c = uuid4(), uuid4(), uuid4()
        edges = [(a, b)]  # c is isolated
        nodes = {a, b, c}

        pr = InternalPageRank._compute_pagerank(edges, nodes)

        # All nodes should have PageRank values
        assert all(v > 0 for v in pr.values())
        assert abs(sum(pr.values()) - 1.0) < 1e-6


# ═══════════════════════════════════════════════
# 4. Content Gap Analysis
# ═══════════════════════════════════════════════


class TestContentGapConstants:
    """Test content gap analysis constants."""

    def test_thresholds_are_reasonable(self):
        from app.services.content_gaps import (
            MIN_IMPRESSIONS_FOR_GAP,
            MAX_CTR_FOR_GAP,
            MAX_POSITION_FOR_GAP,
            MIN_POSITION_FOR_GAP,
        )
        assert MIN_IMPRESSIONS_FOR_GAP == 50
        assert MAX_CTR_FOR_GAP == 0.02
        assert MIN_POSITION_FOR_GAP == 5.0
        assert MAX_POSITION_FOR_GAP == 30.0


# ═══════════════════════════════════════════════
# Import verification
# ═══════════════════════════════════════════════


class TestImports:
    """Verify all new services import cleanly."""

    def test_import_readability(self):
        from app.services.readability import ReadabilityScorer
        assert ReadabilityScorer is not None

    def test_import_pagerank(self):
        from app.services.pagerank import InternalPageRank
        assert InternalPageRank is not None

    def test_import_intent_classifier(self):
        from app.services.intent_classifier import IntentClassifier
        assert IntentClassifier is not None

    def test_import_content_gaps(self):
        from app.services.content_gaps import ContentGapAnalyzer
        assert ContentGapAnalyzer is not None
