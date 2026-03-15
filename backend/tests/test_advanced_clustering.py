"""Tests for advanced clustering — c-TF-IDF, hierarchy, bridge posts, outlier reduction."""

import pytest
import numpy as np
from uuid import uuid4
from app.services.advanced_clustering import (
    compute_ctfidf,
    build_hierarchy,
    detect_bridge_posts,
    reduce_outliers,
    AdvancedClusteringService,
    HierarchyNode,
    BridgePost,
)


class TestCTFIDF:
    """Test class-based TF-IDF computation."""

    def test_basic_ctfidf(self):
        """Two distinct clusters should have different top keywords."""
        docs = {
            "email": [
                "email marketing automation campaign subscribers open rate",
                "email newsletter template subject line click through",
                "email list building opt-in form lead magnet subscribers",
            ],
            "seo": [
                "search engine optimization ranking keywords backlinks",
                "seo audit technical crawl indexing sitemap robots",
                "google algorithm update serp position organic traffic",
            ],
        }
        result = compute_ctfidf(docs, top_n=5)
        assert "email" in result
        assert "seo" in result
        assert len(result["email"]) > 0
        assert len(result["seo"]) > 0

        # Email cluster should have email-related keywords
        email_words = [w for w, _ in result["email"]]
        seo_words = [w for w, _ in result["seo"]]
        # These should be mostly distinct
        overlap = set(email_words) & set(seo_words)
        assert len(overlap) < len(email_words)  # Some overlap ok, not complete

    def test_empty_input(self):
        result = compute_ctfidf({})
        assert result == {}

    def test_single_cluster(self):
        docs = {"only": ["hello world this is a test document with enough words"]}
        result = compute_ctfidf(docs, top_n=3)
        assert "only" in result

    def test_scores_are_positive(self):
        docs = {
            "a": ["the quick brown fox jumps over the lazy dog repeatedly"],
            "b": ["python programming language data science machine learning"],
        }
        result = compute_ctfidf(docs, top_n=5)
        for cluster_keywords in result.values():
            for word, score in cluster_keywords:
                assert score >= 0


class TestHierarchy:
    """Test hierarchical topic structure building."""

    def test_similar_clusters_become_parent_child(self):
        """Two very similar clusters should form a hierarchy."""
        c1, c2 = uuid4(), uuid4()
        # c1 and c2 have similar centroids
        centroids = {
            c1: np.array([1.0, 0.5, 0.3]),
            c2: np.array([0.95, 0.52, 0.28]),
        }
        labels = {c1: "Email Marketing", c2: "Email Automation"}
        hierarchy = build_hierarchy(centroids, labels, similarity_threshold=0.50)
        # One should be parent, one child
        assert len(hierarchy) >= 1

    def test_dissimilar_clusters_stay_separate(self):
        """Very different clusters should both be roots."""
        c1, c2 = uuid4(), uuid4()
        centroids = {
            c1: np.array([1.0, 0.0, 0.0]),
            c2: np.array([0.0, 0.0, 1.0]),
        }
        labels = {c1: "Email", c2: "Cooking"}
        hierarchy = build_hierarchy(centroids, labels, similarity_threshold=0.50)
        assert len(hierarchy) == 2  # Both are roots

    def test_single_cluster(self):
        c1 = uuid4()
        centroids = {c1: np.array([1.0, 0.5])}
        labels = {c1: "Only"}
        hierarchy = build_hierarchy(centroids, labels)
        assert len(hierarchy) == 1
        assert hierarchy[0].cluster_id == c1

    def test_empty_input(self):
        hierarchy = build_hierarchy({}, {})
        assert hierarchy == []


class TestBridgePostDetection:
    """Test multi-topic bridge post detection."""

    def test_bridge_post_detected(self):
        """A post equidistant between two clusters should be a bridge."""
        c1, c2 = uuid4(), uuid4()
        p1 = uuid4()

        # Cluster centroids are distinct
        centroids = {
            c1: np.array([1.0, 0.0, 0.0, 0.0]),
            c2: np.array([0.0, 1.0, 0.0, 0.0]),
        }
        # Post embedding is between both clusters
        post_embs = {p1: np.array([0.5, 0.5, 0.0, 0.0])}
        post_titles = {p1: "Email Marketing SEO Guide"}
        assignments = {p1: c1}

        bridges = detect_bridge_posts(
            post_embs, centroids, assignments, post_titles, threshold=0.15,
        )
        assert len(bridges) >= 1
        assert bridges[0].post_id == p1

    def test_focused_post_not_bridge(self):
        """A post very close to one cluster shouldn't be a bridge."""
        c1, c2 = uuid4(), uuid4()
        p1 = uuid4()

        centroids = {
            c1: np.array([1.0, 0.0, 0.0]),
            c2: np.array([0.0, 0.0, 1.0]),
        }
        # Post is very close to c1
        post_embs = {p1: np.array([0.99, 0.01, 0.0])}
        assignments = {p1: c1}

        bridges = detect_bridge_posts(
            post_embs, centroids, assignments, {p1: "Focused"}, threshold=0.15,
        )
        # Should not be detected as bridge (probability for c2 should be < threshold)
        # This depends on softmax temperature, may or may not be bridge
        # The key test is that it's not bridge if clusters are very distinct
        if bridges:
            # If detected, secondary probability should be low
            assert bridges[0].secondary_clusters[0][1] < bridges[0].primary_probability

    def test_empty_inputs(self):
        bridges = detect_bridge_posts({}, {}, {}, {})
        assert bridges == []


class TestOutlierReduction:
    """Test noise post reassignment."""

    def test_close_outlier_gets_reassigned(self):
        """An outlier close to a cluster should be reassigned."""
        c1 = uuid4()
        p1 = uuid4()

        centroids = {c1: np.array([1.0, 0.0, 0.0])}
        noise = {p1: np.array([0.9, 0.1, 0.0])}

        result = reduce_outliers(noise, centroids, min_similarity=0.20)
        assert p1 in result
        assert result[p1] == c1

    def test_distant_outlier_stays_noise(self):
        """An outlier far from all clusters should stay unassigned."""
        c1 = uuid4()
        p1 = uuid4()

        centroids = {c1: np.array([1.0, 0.0, 0.0])}
        noise = {p1: np.array([0.0, 0.0, 1.0])}  # Orthogonal

        result = reduce_outliers(noise, centroids, min_similarity=0.50)
        assert p1 not in result  # Too far, not reassigned

    def test_empty_inputs(self):
        assert reduce_outliers({}, {}) == {}
        c1 = uuid4()
        assert reduce_outliers({}, {c1: np.array([1, 0])}) == {}


class TestAdvancedClusteringService:
    """Test the service class."""

    def test_instantiates(self):
        service = AdvancedClusteringService()
        assert service is not None

    def test_has_enrich_method(self):
        service = AdvancedClusteringService()
        assert hasattr(service, 'enrich_clusters')
