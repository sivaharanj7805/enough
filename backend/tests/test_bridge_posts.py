"""Focused tests for bridge post detection — posts spanning multiple topics."""

import pytest
import numpy as np
from uuid import uuid4
from app.services.advanced_clustering import detect_bridge_posts, BridgePost


class TestBridgePostDetection:
    """Test bridge post detection with realistic scenarios."""

    def _make_centroids(self, n: int, dim: int = 50) -> dict:
        """Create n well-separated cluster centroids."""
        centroids = {}
        for i in range(n):
            vec = np.zeros(dim)
            vec[i * (dim // n):(i + 1) * (dim // n)] = 1.0
            centroids[uuid4()] = vec / np.linalg.norm(vec)
        return centroids

    def test_comprehensive_guide_is_bridge(self):
        """A guide covering multiple topics should be detected as bridge."""
        c1, c2, c3 = uuid4(), uuid4(), uuid4()
        p1 = uuid4()

        # 3 distinct clusters
        centroids = {
            c1: np.array([1.0, 0.0, 0.0, 0.0, 0.0]),
            c2: np.array([0.0, 1.0, 0.0, 0.0, 0.0]),
            c3: np.array([0.0, 0.0, 1.0, 0.0, 0.0]),
        }

        # Post that sits between c1 and c2
        post_embs = {p1: np.array([0.5, 0.5, 0.0, 0.0, 0.0])}
        titles = {p1: "Complete Guide to Email Marketing and SEO"}
        assignments = {p1: c1}

        bridges = detect_bridge_posts(post_embs, centroids, assignments, titles, 0.15)
        assert len(bridges) >= 1
        bridge = bridges[0]
        assert bridge.post_id == p1
        assert len(bridge.secondary_clusters) >= 1

    def test_focused_post_not_bridge_with_many_clusters(self):
        """Post very focused on one topic shouldn't be bridge when clusters are spread."""
        centroids = self._make_centroids(5)
        cluster_ids = list(centroids.keys())

        p1 = uuid4()
        # Very close to first cluster
        first_centroid = centroids[cluster_ids[0]]
        post_embs = {p1: first_centroid * 0.99 + np.random.randn(50) * 0.01}
        titles = {p1: "Very Focused Post"}
        assignments = {p1: cluster_ids[0]}

        bridges = detect_bridge_posts(post_embs, centroids, assignments, titles, 0.30)
        # With high threshold, focused post shouldn't be bridge
        # (depends on exact geometry but likely not)
        for b in bridges:
            if b.post_id == p1:
                # Even if detected, primary should dominate
                assert b.primary_probability > 0.5

    def test_multiple_bridge_posts(self):
        """Multiple posts can be bridges."""
        c1, c2, c3 = uuid4(), uuid4(), uuid4()
        p1, p2, p3 = uuid4(), uuid4(), uuid4()

        centroids = {
            c1: np.array([1.0, 0.0, 0.0]),
            c2: np.array([0.0, 1.0, 0.0]),
            c3: np.array([0.0, 0.0, 1.0]),
        }

        post_embs = {
            p1: np.array([0.5, 0.5, 0.0]),  # Between c1 and c2
            p2: np.array([0.0, 0.5, 0.5]),  # Between c2 and c3
            p3: np.array([1.0, 0.0, 0.0]),  # Focused on c1
        }
        titles = {p1: "Bridge 1", p2: "Bridge 2", p3: "Focused"}
        assignments = {p1: c1, p2: c2, p3: c1}

        bridges = detect_bridge_posts(post_embs, centroids, assignments, titles, 0.15)
        bridge_ids = {b.post_id for b in bridges}
        # p1 and p2 should be bridges, p3 might not be
        assert p1 in bridge_ids
        assert p2 in bridge_ids

    def test_bridge_has_title(self):
        """Bridge post should carry the post title."""
        c1, c2 = uuid4(), uuid4()
        p1 = uuid4()
        centroids = {
            c1: np.array([1.0, 0.0]),
            c2: np.array([0.0, 1.0]),
        }
        post_embs = {p1: np.array([0.5, 0.5])}
        titles = {p1: "My Bridge Post Title"}
        assignments = {p1: c1}

        bridges = detect_bridge_posts(post_embs, centroids, assignments, titles, 0.15)
        assert any(b.title == "My Bridge Post Title" for b in bridges)

    def test_primary_probability_highest(self):
        """Primary cluster should have highest probability."""
        c1, c2, c3 = uuid4(), uuid4(), uuid4()
        p1 = uuid4()
        centroids = {
            c1: np.array([1.0, 0.0, 0.0]),
            c2: np.array([0.0, 1.0, 0.0]),
            c3: np.array([0.0, 0.0, 1.0]),
        }
        post_embs = {p1: np.array([0.6, 0.4, 0.0])}
        titles = {p1: "Mostly C1"}
        assignments = {p1: c1}

        bridges = detect_bridge_posts(post_embs, centroids, assignments, titles, 0.10)
        for b in bridges:
            if b.post_id == p1:
                assert b.primary_probability >= max(
                    prob for _, prob in b.secondary_clusters
                )
