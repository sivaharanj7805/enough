"""Tests for BM25 keyword overlap signal."""

import math
import pytest
from uuid import uuid4
from app.services.bm25_signal import (
    tokenize,
    compute_bm25_pairwise,
    reciprocal_rank_fusion,
    classify_triple_signal,
    RRF_K,
    BM25_THRESHOLD,
)


class TestTokenizer:
    """Test the tokenizer."""

    def test_lowercases(self):
        tokens = tokenize("Hello World Python")
        assert "hello" in tokens
        assert "world" in tokens
        assert "python" in tokens

    def test_removes_punctuation(self):
        tokens = tokenize("email-marketing, SEO! strategy.")
        assert "email" in tokens
        assert "marketing" in tokens
        assert "seo" in tokens

    def test_removes_stop_words(self):
        tokens = tokenize("the quick brown fox is a very good animal")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "very" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens

    def test_removes_short_tokens(self):
        tokens = tokenize("a b c de fg hello world")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "de" not in tokens

    def test_empty_string(self):
        assert tokenize("") == []
        assert tokenize("the a is") == []


class TestBM25Pairwise:
    """Test BM25 pairwise scoring."""

    def test_similar_docs_score_high(self):
        """Documents about the same topic should score higher."""
        p1, p2, p3 = uuid4(), uuid4(), uuid4()
        texts = {
            p1: "email marketing automation campaign subscribers list building",
            p2: "email marketing strategy newsletter subscribers engagement",
            p3: "python programming machine learning data science tensorflow",
        }
        scores = compute_bm25_pairwise([p1, p2, p3], texts)

        # Email pair should score higher than email vs python
        email_pair = scores.get((p1, p2), 0)
        cross_pair_1 = scores.get((p1, p3), 0)
        cross_pair_2 = scores.get((p2, p3), 0)
        assert email_pair > cross_pair_1
        assert email_pair > cross_pair_2

    def test_empty_corpus(self):
        scores = compute_bm25_pairwise([], {})
        assert scores == {}

    def test_single_post(self):
        p1 = uuid4()
        scores = compute_bm25_pairwise([p1], {p1: "hello world"})
        assert scores == {}

    def test_symmetric_scores(self):
        """Score for (A,B) should be same key regardless of order."""
        p1, p2 = uuid4(), uuid4()
        texts = {
            p1: "email marketing automation campaigns",
            p2: "email newsletter design templates",
        }
        scores = compute_bm25_pairwise([p1, p2], texts)
        # Only one key per pair (ordered by iteration)
        assert len(scores) == 1

    def test_scores_are_finite(self):
        """BM25Okapi can return slightly negative scores for dissimilar docs — that's normal."""
        p1, p2 = uuid4(), uuid4()
        texts = {
            p1: "content marketing strategy blog optimization",
            p2: "search engine optimization ranking keywords",
        }
        scores = compute_bm25_pairwise([p1, p2], texts)
        for score in scores.values():
            assert math.isfinite(score)


class TestRRF:
    """Test Reciprocal Rank Fusion."""

    def test_basic_fusion(self):
        pair = (uuid4(), uuid4())
        cosine_ranks = {pair: 1}
        jaccard_ranks = {pair: 1}
        bm25_ranks = {pair: 1}

        result = reciprocal_rank_fusion(cosine_ranks, jaccard_ranks, bm25_ranks)
        assert pair in result
        expected = 3 * (1.0 / (RRF_K + 1))
        assert abs(result[pair] - expected) < 0.0001

    def test_higher_rrf_for_consistently_ranked(self):
        """A pair ranked #1 on all signals should score higher than one ranked #5."""
        pair_good = (uuid4(), uuid4())
        pair_bad = (uuid4(), uuid4())

        cosine_ranks = {pair_good: 1, pair_bad: 5}
        jaccard_ranks = {pair_good: 1, pair_bad: 5}
        bm25_ranks = {pair_good: 1, pair_bad: 5}

        result = reciprocal_rank_fusion(cosine_ranks, jaccard_ranks, bm25_ranks)
        assert result[pair_good] > result[pair_bad]

    def test_missing_signal_gets_max_rank(self):
        """Pairs missing from one signal should still get a score."""
        pair = (uuid4(), uuid4())
        cosine_ranks = {pair: 1}
        # Not in jaccard or bm25
        result = reciprocal_rank_fusion(cosine_ranks, {}, {})
        assert pair in result
        assert result[pair] > 0


class TestTripleSignalClassification:
    """Test severity classification."""

    def test_all_three_signals_critical(self):
        signals, severity = classify_triple_signal(0.60, 0.20, 10.0)
        assert signals == 3
        assert severity == "critical"

    def test_two_signals_high(self):
        signals, severity = classify_triple_signal(0.50, 0.15, 1.0)
        assert signals == 2
        assert severity == "high"

    def test_one_signal_medium(self):
        signals, severity = classify_triple_signal(0.50, 0.05, 1.0)
        assert signals == 1
        assert severity == "medium"

    def test_no_signals_low(self):
        signals, severity = classify_triple_signal(0.20, 0.05, 1.0)
        assert signals == 0
        assert severity == "low"

    def test_custom_thresholds(self):
        signals, severity = classify_triple_signal(
            0.30, 0.08, 3.0,
            cosine_threshold=0.25, jaccard_threshold=0.05, bm25_threshold=2.0,
        )
        assert signals == 3
        assert severity == "critical"
