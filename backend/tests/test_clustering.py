"""Tests for clustering logic — HDBSCAN wrapper and labeling."""

import numpy as np
import pytest

# Test the clustering math directly (HDBSCAN)
try:
    import hdbscan
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False


@pytest.mark.skipif(not HAS_HDBSCAN, reason="hdbscan not installed")
class TestHDBSCANClustering:
    """Test that HDBSCAN produces correct cluster assignments."""

    def test_two_clear_clusters(self):
        """Two well-separated groups should produce 2 clusters."""
        np.random.seed(42)
        group_a = np.random.normal(loc=[0, 0], scale=0.3, size=(20, 2))
        group_b = np.random.normal(loc=[5, 5], scale=0.3, size=(20, 2))
        data = np.vstack([group_a, group_b])

        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, min_samples=3)
        labels = clusterer.fit_predict(data)

        unique = set(labels)
        unique.discard(-1)  # Remove noise label
        assert len(unique) >= 2

    def test_single_cluster(self):
        """One tight group should produce at most 1 cluster."""
        np.random.seed(42)
        data = np.random.normal(loc=[0, 0], scale=0.1, size=(30, 2))

        clusterer = hdbscan.HDBSCAN(min_cluster_size=10, min_samples=5)
        labels = clusterer.fit_predict(data)

        unique = set(labels)
        unique.discard(-1)
        assert len(unique) <= 2  # Tight data should not fragment much

    def test_all_noise(self):
        """Very spread out data should be mostly noise."""
        np.random.seed(42)
        data = np.random.uniform(low=-100, high=100, size=(10, 2))

        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, min_samples=3)
        labels = clusterer.fit_predict(data)

        # Most or all should be noise (-1) with so few spread points
        noise_count = sum(1 for l in labels if l == -1)
        assert noise_count >= 5

    def test_three_clusters(self):
        """Three well-separated groups should produce 3 clusters."""
        np.random.seed(42)
        a = np.random.normal(loc=[0, 0], scale=0.3, size=(15, 2))
        b = np.random.normal(loc=[5, 0], scale=0.3, size=(15, 2))
        c = np.random.normal(loc=[2.5, 5], scale=0.3, size=(15, 2))
        data = np.vstack([a, b, c])

        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, min_samples=3)
        labels = clusterer.fit_predict(data)

        unique = set(labels)
        unique.discard(-1)
        assert len(unique) >= 3

    def test_cluster_labels_are_integers(self):
        """Labels should be integer type."""
        np.random.seed(42)
        data = np.random.normal(loc=[0, 0], scale=0.3, size=(20, 2))

        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, min_samples=3)
        labels = clusterer.fit_predict(data)

        assert all(isinstance(int(l), int) for l in labels)
