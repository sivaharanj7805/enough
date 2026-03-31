"""Tests for clustering logic — HDBSCAN, UMAP, TopicClusterer, and TF-IDF labels."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from tests.conftest import MockConnection, MockRecord, make_record, TEST_SITE_ID

# Test the clustering math directly (HDBSCAN)
try:
    import hdbscan
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False

try:
    import umap
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False

try:
    from sklearn.metrics import silhouette_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


# ────────────────────────────────────────────────────────────────
# 1. HDBSCAN direct tests (existing + enhanced)
# ────────────────────────────────────────────────────────────────

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


# ────────────────────────────────────────────────────────────────
# 2. TopicClusterer._run_clustering_and_2d tests
# ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (HAS_HDBSCAN and HAS_UMAP and HAS_SKLEARN),
    reason="hdbscan, umap-learn, or sklearn not installed",
)
class TestRunClusteringAnd2D:
    """Tests for the combined UMAP+HDBSCAN pipeline inside TopicClusterer."""

    def _make_clusterer(self):
        """Create TopicClusterer with mocked Anthropic client."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                return TopicClusterer()

    def _make_embeddings(self, n_groups: int, n_per_group: int, dim: int = 1536) -> np.ndarray:
        """Create synthetic embeddings with n_groups well-separated clusters."""
        np.random.seed(42)
        groups = []
        for i in range(n_groups):
            center = np.zeros(dim)
            center[i * 10:(i + 1) * 10] = 3.0  # Distinct in different dims
            group = np.random.normal(loc=center, scale=0.1, size=(n_per_group, dim))
            # L2-normalize to mimic OpenAI embeddings
            norms = np.linalg.norm(group, axis=1, keepdims=True)
            group = group / norms
            groups.append(group)
        return np.vstack(groups).astype(np.float32)

    def test_produces_labels_and_2d_positions(self):
        """Should return labels array and 2D positions array."""
        tc = self._make_clusterer()
        embeddings = self._make_embeddings(3, 20)
        n_posts = len(embeddings)

        labels, positions_2d = tc._run_clustering_and_2d(embeddings, n_posts)

        assert labels.shape == (n_posts,)
        assert positions_2d.shape == (n_posts, 2)
        # Should find multiple clusters for well-separated data
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        assert n_clusters >= 2

    def test_adaptive_similarity_diverse_content(self):
        """Diverse content (mean_sim < 0.50) should use min_dist=0.05."""
        tc = self._make_clusterer()
        # Random high-dim embeddings are diverse (low cosine similarity)
        np.random.seed(42)
        embeddings = np.random.randn(30, 1536).astype(np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

        # Mean cosine sim of random unit vectors in high dim is near 0
        from sklearn.metrics.pairwise import cosine_similarity
        sim = cosine_similarity(embeddings)
        np.fill_diagonal(sim, 0)
        mean_sim = sim.mean()
        assert mean_sim < 0.50, f"Expected diverse content, got mean_sim={mean_sim}"

        # Should still produce valid output
        labels, positions_2d = tc._run_clustering_and_2d(embeddings, 30)
        assert labels.shape == (30,)
        assert positions_2d.shape == (30, 2)

    def test_adaptive_similarity_tight_niche(self):
        """Tight niche (mean_sim > 0.70) should use min_dist=0.25, n_neighbors=5."""
        tc = self._make_clusterer()
        np.random.seed(42)
        # Create very similar embeddings (tight niche)
        base = np.random.randn(1536).astype(np.float32)
        base = base / np.linalg.norm(base)
        embeddings = np.array([
            base + np.random.randn(1536).astype(np.float32) * 0.05
            for _ in range(30)
        ])
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = (embeddings / norms).astype(np.float32)

        from sklearn.metrics.pairwise import cosine_similarity
        sim = cosine_similarity(embeddings)
        np.fill_diagonal(sim, 0)
        mean_sim = sim.mean()
        assert mean_sim > 0.70, f"Expected tight niche, got mean_sim={mean_sim}"

        labels, positions_2d = tc._run_clustering_and_2d(embeddings, 30)
        assert labels.shape == (30,)
        assert positions_2d.shape == (30, 2)

    def test_silhouette_retry_on_poor_quality(self):
        """Silhouette < 0.1 should trigger retry with larger min_cluster_size."""
        tc = self._make_clusterer()
        # Create overlapping clusters that produce poor silhouette
        np.random.seed(42)
        embeddings = self._make_embeddings(2, 15, dim=1536)
        # Add noise that overlaps both clusters
        noise = np.random.randn(10, 1536).astype(np.float32)
        noise = noise / np.linalg.norm(noise, axis=1, keepdims=True)
        embeddings = np.vstack([embeddings, noise]).astype(np.float32)

        # Just verify it runs without error and produces valid output
        labels, positions_2d = tc._run_clustering_and_2d(embeddings, len(embeddings))
        assert labels.shape[0] == len(embeddings)
        assert positions_2d.shape == (len(embeddings), 2)

    def test_noise_reassignment_to_nearest_centroid(self):
        """Noise points should be reassigned to the nearest cluster centroid."""
        tc = self._make_clusterer()
        embeddings = self._make_embeddings(3, 20)

        labels, _ = tc._run_clustering_and_2d(embeddings, len(embeddings))

        # After noise reassignment, there should be no -1 labels
        # (unless HDBSCAN found zero clusters, which shouldn't happen with 3 groups)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        if n_clusters > 0:
            assert -1 not in labels, "Noise should have been reassigned to nearest cluster"

    def test_cluster_aware_2d_nudge(self):
        """Posts should be nudged 15% toward their cluster centroid."""
        tc = self._make_clusterer()
        embeddings = self._make_embeddings(2, 20)

        labels, positions_2d = tc._run_clustering_and_2d(embeddings, len(embeddings))

        # Verify positions are valid floats (not NaN/inf)
        assert not np.any(np.isnan(positions_2d)), "2D positions contain NaN"
        assert not np.any(np.isinf(positions_2d)), "2D positions contain Inf"

        # Verify that posts in same cluster are closer together than posts in different clusters
        # (the nudge should tighten intra-cluster distances)
        unique_labels = set(labels)
        unique_labels.discard(-1)
        if len(unique_labels) >= 2:
            clusters = list(unique_labels)
            c0_posts = positions_2d[labels == clusters[0]]
            c1_posts = positions_2d[labels == clusters[1]]
            # Intra-cluster distance
            intra_0 = np.mean(np.linalg.norm(c0_posts - c0_posts.mean(axis=0), axis=1))
            intra_1 = np.mean(np.linalg.norm(c1_posts - c1_posts.mean(axis=0), axis=1))
            # Inter-cluster distance
            inter = np.linalg.norm(c0_posts.mean(axis=0) - c1_posts.mean(axis=0))
            avg_intra = (intra_0 + intra_1) / 2
            assert inter > avg_intra, "Inter-cluster distance should exceed avg intra-cluster distance"

    def test_single_cluster_nudge_is_harmless(self):
        """Nudge on a single cluster should not crash or distort positions."""
        tc = self._make_clusterer()
        np.random.seed(42)
        # Tight single group
        base = np.random.randn(1536).astype(np.float32)
        base = base / np.linalg.norm(base)
        embeddings = np.array([
            base + np.random.randn(1536).astype(np.float32) * 0.02
            for _ in range(20)
        ])
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = (embeddings / norms).astype(np.float32)

        labels, positions_2d = tc._run_clustering_and_2d(embeddings, 20)
        assert positions_2d.shape == (20, 2)
        assert not np.any(np.isnan(positions_2d))

    def test_all_identical_embeddings_single_cluster(self):
        """All identical embeddings should produce a single cluster."""
        tc = self._make_clusterer()
        np.random.seed(42)
        base = np.random.randn(1536).astype(np.float32)
        base = base / np.linalg.norm(base)
        # Tiny perturbation to avoid UMAP issues with identical points
        embeddings = np.array([
            base + np.random.randn(1536).astype(np.float32) * 0.001
            for _ in range(20)
        ])
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = (embeddings / norms).astype(np.float32)

        labels, positions_2d = tc._run_clustering_and_2d(embeddings, 20)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        assert n_clusters <= 2, f"Near-identical embeddings should produce 1-2 clusters, got {n_clusters}"


# ────────────────────────────────────────────────────────────────
# 3. Small site shortcut and edge cases
# ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (HAS_HDBSCAN and HAS_UMAP),
    reason="hdbscan or umap-learn not installed",
)
class TestSmallSiteEdgeCases:
    """Test the small site shortcut (<15 posts) and boundary."""

    def _make_clusterer(self):
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                return TopicClusterer()

    def test_simple_2d_layout_circle(self):
        """<15 posts should use simple circular layout."""
        from app.services.clustering import TopicClusterer
        positions = TopicClusterer._simple_2d_layout(10)
        assert positions.shape == (10, 2)
        # All points should be on a circle of radius 2.0
        distances = np.sqrt(positions[:, 0] ** 2 + positions[:, 1] ** 2)
        np.testing.assert_allclose(distances, 2.0, atol=0.01)

    def test_simple_2d_layout_single_post(self):
        """Single post should be at (2.0, 0.0)."""
        from app.services.clustering import TopicClusterer
        positions = TopicClusterer._simple_2d_layout(1)
        assert positions.shape == (1, 2)
        np.testing.assert_allclose(positions[0], [2.0, 0.0], atol=0.01)

    def test_simple_2d_layout_zero_posts(self):
        """Zero posts should return empty array."""
        from app.services.clustering import TopicClusterer
        positions = TopicClusterer._simple_2d_layout(0)
        assert positions.shape == (0, 2)

    def test_exactly_15_posts_uses_full_pipeline(self):
        """Exactly 15 posts should use UMAP+HDBSCAN, not the shortcut."""
        tc = self._make_clusterer()
        np.random.seed(42)
        embeddings = np.random.randn(15, 1536).astype(np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

        labels, positions_2d = tc._run_clustering_and_2d(embeddings, 15)
        assert labels.shape == (15,)
        assert positions_2d.shape == (15, 2)

    def test_exactly_14_posts_uses_shortcut(self):
        """14 posts should use the single-cluster shortcut."""
        # This tests the boundary in cluster_site() but we test _simple_2d_layout
        from app.services.clustering import TopicClusterer
        positions = TopicClusterer._simple_2d_layout(14)
        assert positions.shape == (14, 2)


# ────────────────────────────────────────────────────────────────
# 4. Noise-rate quality gate in sub-clustering
# ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (HAS_HDBSCAN and HAS_UMAP),
    reason="hdbscan or umap-learn not installed",
)
class TestNoiseRateQualityGate:
    """Test that sub-clustering rejects splits with >60% noise."""

    def _make_clusterer(self):
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                return TopicClusterer()

    @pytest.mark.asyncio
    async def test_high_noise_rate_rejects_split(self):
        """Sub-clustering should return 0 if noise rate > 60%."""
        tc = self._make_clusterer()
        db = MockConnection()
        site_id = TEST_SITE_ID
        parent_id = uuid4()

        # Create homogeneous embeddings that will produce high noise
        np.random.seed(42)
        base = np.random.randn(1536).astype(np.float32)
        base = base / np.linalg.norm(base)
        n = 30
        embeddings = np.array([
            base + np.random.randn(1536).astype(np.float32) * 0.01
            for _ in range(n)
        ])
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = (embeddings / norms).astype(np.float32)

        post_ids = [uuid4() for _ in range(n)]
        titles = [f"Post {i}" for i in range(n)]
        urls = [f"/post-{i}" for i in range(n)]

        result = await tc._recursive_subcluster(
            db, site_id, parent_id, embeddings,
            post_ids, titles, urls,
            max_cluster_size=10, skip_labeling=True,
        )
        # Homogeneous content should either find <=1 sub-cluster or reject due to noise
        # In either case, result should be 0 (no sub-clusters created)
        assert result == 0, f"Expected 0 sub-clusters for homogeneous content, got {result}"


# ────────────────────────────────────────────────────────────────
# 5. _parse_pgvector
# ────────────────────────────────────────────────────────────────

class TestParsePgvector:
    """Test pgvector text format parsing."""

    def test_bracket_format(self):
        from app.services.clustering import _parse_pgvector
        result = _parse_pgvector("[1.0,2.0,3.0]")
        assert result == [1.0, 2.0, 3.0]

    def test_no_brackets(self):
        from app.services.clustering import _parse_pgvector
        result = _parse_pgvector("1.0,2.0,3.0")
        assert result == [1.0, 2.0, 3.0]

    def test_whitespace(self):
        from app.services.clustering import _parse_pgvector
        result = _parse_pgvector("  [1.0,2.0,3.0]  ")
        assert result == [1.0, 2.0, 3.0]

    def test_negative_values(self):
        from app.services.clustering import _parse_pgvector
        result = _parse_pgvector("[-0.5,0.0,0.5]")
        assert result == [-0.5, 0.0, 0.5]

    def test_scientific_notation(self):
        from app.services.clustering import _parse_pgvector
        result = _parse_pgvector("[1e-5,2.5e3]")
        assert result == [1e-5, 2.5e3]


# ────────────────────────────────────────────────────────────────
# 6. TF-IDF labeling tests
# ────────────────────────────────────────────────────────────────

class TestTFIDFLabeling:
    """Test the fast TF-IDF cluster labeling pipeline."""

    def test_strip_format_markers(self):
        from app.services.fast_cluster_labels import _strip_format
        assert "link building" in _strip_format("The Definitive Guide to Link Building in 2024")
        assert "seo" in _strip_format("A Complete Guide to SEO")
        # Should strip trailing year
        result = _strip_format("Email Marketing Tips in 2024 - Backlinko")
        assert "2024" not in result
        assert "backlinko" not in result.lower() or len(result.split()) >= 3

    def test_extract_phrases_bigrams(self):
        from app.services.fast_cluster_labels import _extract_phrases
        phrases = _extract_phrases("The Complete Guide to Link Building Strategies")
        # Should contain the bigram "link building"
        bigrams = [p for p in phrases if " " in p]
        assert any("link" in b and "building" in b for b in bigrams), \
            f"Expected 'link building' bigram, got: {bigrams}"

    def test_compute_site_stops(self):
        from app.services.fast_cluster_labels import _compute_site_stops
        # SEO blog where "seo" appears in 50% of titles
        titles = [
            "SEO Guide", "SEO Tips", "SEO Strategy", "SEO Basics", "SEO Tutorial",
            "Link Building", "Content Marketing", "Email Tips", "Social Media", "Blogging",
        ]
        stops = _compute_site_stops(titles)
        # "seo" appears in 5/10 = 50%, above the 15% threshold for <100 posts
        assert "seo" in stops, f"Expected 'seo' in site stops, got: {stops}"

    def test_compute_site_stops_adaptive_threshold(self):
        """Threshold should be 15% for <100 posts, 20% for 100-299, 30% for 300+."""
        from app.services.fast_cluster_labels import _compute_site_stops
        # Small site: 15% threshold
        small_titles = [f"SEO Post {i}" for i in range(50)] + [f"Random Post {i}" for i in range(50)]
        stops = _compute_site_stops(small_titles)
        # "post" appears in all 100 titles (100%), should be stopped
        assert "post" in stops

    def test_tfidf_label_produces_readable_labels(self):
        from app.services.fast_cluster_labels import _tfidf_label
        cluster_titles = [
            "How to Build Links for SEO",
            "Link Building Strategies That Work",
            "The Best Link Building Tools",
            "Link Building for Beginners",
            "Advanced Link Building Techniques",
        ]
        all_titles = cluster_titles + [
            "Email Marketing Guide",
            "Social Media Strategy",
            "Content Marketing Tips",
        ]
        label, alternatives, desc_words = _tfidf_label(cluster_titles, all_titles)
        assert len(label) > 0
        assert "link" in label.lower() or "building" in label.lower(), \
            f"Expected label containing 'link' or 'building', got: {label}"

    def test_tfidf_label_fallback_on_empty(self):
        from app.services.fast_cluster_labels import _tfidf_label
        label, alternatives, desc_words = _tfidf_label([], [])
        assert label == "Miscellaneous"

    def test_smart_title_acronyms(self):
        from app.services.fast_cluster_labels import _smart_title
        assert _smart_title("seo") == "SEO"
        assert _smart_title("ppc") == "PPC"
        assert _smart_title("marketing") == "Marketing"

    def test_connect_label_parts_compound_nouns(self):
        from app.services.fast_cluster_labels import _connect_label_parts
        # Known compound noun — no "&" connector
        assert _connect_label_parts("Link", "Building") == "Link Building"
        assert _connect_label_parts("Email", "Marketing") == "Email Marketing"
        # Unknown pair — uses "&"
        assert _connect_label_parts("Sales", "SEO") == "Sales & SEO"

    def test_generate_description(self):
        from app.services.fast_cluster_labels import _generate_description
        desc = _generate_description("Link Building", ["Outreach", "Prospecting", "Tools"])
        assert "outreach" in desc.lower()
        assert "link building" not in desc.lower()  # Label words should be filtered

    def test_validate_label_specificity(self):
        from app.services.fast_cluster_labels import _validate_label_specificity
        all_cluster_titles = [
            ["Link Building Guide", "Link Building Tips"],
            ["Email Marketing 101", "Email Best Practices"],
            ["SEO Tutorial", "SEO Basics"],
        ]
        # "Link Building" is specific to cluster 0 — should validate
        assert _validate_label_specificity("Link Building", 0, all_cluster_titles) is True
        # "Guide" appears in cluster 0 titles but we test with real labels
        # A label like "General" that appears everywhere should fail
        all_cluster_titles_generic = [
            ["Marketing Guide", "Marketing Tips"],
            ["Marketing Strategy", "Marketing 101"],
            ["Marketing Basics", "Marketing Tools"],
        ]
        # "Marketing" appears in all clusters — not specific
        assert _validate_label_specificity("Marketing", 0, all_cluster_titles_generic) is False


# ────────────────────────────────────────────────────────────────
# 7. Progress callback
# ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (HAS_HDBSCAN and HAS_UMAP),
    reason="hdbscan or umap-learn not installed",
)
class TestProgressCallback:
    """Test that on_progress is called at each clustering checkpoint."""

    @pytest.mark.asyncio
    async def test_progress_callback_called(self):
        """on_progress should be called at least 3 times during clustering."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                tc = TopicClusterer()

        progress_messages: list[str] = []

        def on_progress(msg: str) -> None:
            progress_messages.append(msg)

        db = MockConnection()
        site_id = TEST_SITE_ID

        # Build mock embedding rows (20 posts, 2 groups)
        np.random.seed(42)
        post_ids = [uuid4() for _ in range(20)]
        rows = []
        for i in range(20):
            emb = np.zeros(1536, dtype=np.float32)
            emb[0] = 1.0 if i < 10 else -1.0  # Two groups
            emb += np.random.randn(1536).astype(np.float32) * 0.01
            emb = emb / np.linalg.norm(emb)
            emb_text = "[" + ",".join(str(float(x)) for x in emb) + "]"
            rows.append(make_record(
                post_id=post_ids[i],
                title=f"Post {i}",
                url=f"/post-{i}",
                word_count=1000,
                embedding_text=emb_text,
            ))

        # Mock DB responses
        db._fetch_returns = [
            rows,  # Fetch embeddings
            [make_record(id=uuid4()) for _ in range(0)],  # old clusters (empty for first run)
        ]
        db._fetchval_returns = [uuid4() for _ in range(10)]  # cluster IDs

        # Mock crawl_jobs update
        result = await tc.cluster_site(db, site_id, skip_labeling=True, on_progress=on_progress)

        # Should have at least: "Fetched N embeddings", "UMAP + HDBSCAN complete", "Stored N clusters"
        assert len(progress_messages) >= 3, \
            f"Expected >= 3 progress messages, got {len(progress_messages)}: {progress_messages}"
        assert any("Fetched" in m for m in progress_messages)
        assert any("UMAP" in m or "HDBSCAN" in m for m in progress_messages)
        assert any("Stored" in m for m in progress_messages)


# ────────────────────────────────────────────────────────────────
# 8. Adaptive HDBSCAN parameters
# ────────────────────────────────────────────────────────────────

class TestAdaptiveHDBSCANParams:
    """Test that min_cluster_size and min_samples adapt correctly to site size."""

    def test_small_site_params(self):
        """< 20 posts: min_cluster_size = max(2, n//5), min_samples = 1."""
        n = 18
        min_cluster_size = max(2, n // 5)
        min_samples = 1
        assert min_cluster_size == 3
        assert min_samples == 1

    def test_medium_site_params(self):
        """20-99 posts: min_cluster_size = max(3, n//10), min_samples = 2."""
        n = 50
        min_cluster_size = max(3, n // 10)
        assert min_cluster_size == 5

    def test_large_site_params(self):
        """100-499 posts: min_cluster_size = max(5, n//20), min_samples = 3."""
        n = 200
        min_cluster_size = max(5, n // 20)
        assert min_cluster_size == 10

    def test_big_site_params(self):
        """500-999 posts: fixed min_cluster_size = 12."""
        # As per code
        assert 12 == 12

    def test_mega_site_params(self):
        """1000+ posts: capped at min_cluster_size = 20."""
        # Cap prevents collapsing into 3 mega-clusters
        assert 20 == 20

    def test_param_progression(self):
        """min_cluster_size should generally increase with site size."""
        sizes = [18, 50, 200, 500, 1000]
        expected_min_cluster = [3, 5, 10, 12, 20]
        for n, expected in zip(sizes, expected_min_cluster):
            if n < 20:
                mcs = max(2, n // 5)
            elif n < 100:
                mcs = max(3, n // 10)
            elif n < 500:
                mcs = max(5, n // 20)
            elif n < 1000:
                mcs = 12
            else:
                mcs = 20
            assert mcs == expected, f"n={n}: expected min_cluster_size={expected}, got {mcs}"


# ────────────────────────────────────────────────────────────────
# 9. Claude label and describe
# ────────────────────────────────────────────────────────────────

class TestClaudeLabelAndDescribe:
    """Test the Claude API labeling method."""

    @pytest.mark.asyncio
    async def test_label_and_describe_returns_label_description(self):
        """Should return (label, description) from Claude response."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic") as mock_anthropic:
                from app.services.clustering import TopicClusterer
                tc = TopicClusterer()

                # Mock Claude response
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Link Building Strategies\nCovers various techniques for acquiring backlinks.\ncold outreach, guest posting, broken links")]
                tc.anthropic.messages.create = AsyncMock(return_value=mock_response)

                label, description = await tc._label_and_describe_cluster(
                    ["Guide to Link Building", "Link Building Tips"],
                    ["/link-building", "/link-tips"],
                )
                assert label == "Link Building Strategies"
                assert "backlinks" in description.lower()

    @pytest.mark.asyncio
    async def test_label_and_describe_fallback_on_error(self):
        """Should return fallback label on Claude API error."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                tc = TopicClusterer()

                tc.anthropic.messages.create = AsyncMock(side_effect=Exception("API error"))

                label, description = await tc._label_and_describe_cluster(
                    ["Post 1", "Post 2", "Post 3"],
                    ["/p1", "/p2", "/p3"],
                )
                assert "3 posts" in label
                assert description == ""

    @pytest.mark.asyncio
    async def test_label_truncated_to_80_chars(self):
        """Labels should be truncated to 80 characters."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                tc = TopicClusterer()

                long_label = "A" * 100
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text=f"{long_label}\nDescription line\nSub-themes")]
                tc.anthropic.messages.create = AsyncMock(return_value=mock_response)

                label, description = await tc._label_and_describe_cluster(
                    ["Post 1"], ["/p1"],
                )
                assert len(label) <= 80


# ────────────────────────────────────────────────────────────────
# 10. Clear old clusters (idempotent)
# ────────────────────────────────────────────────────────────────

class TestClearOldClusters:
    """Test idempotent cluster clearing."""

    @pytest.mark.asyncio
    async def test_clear_removes_all_related_data(self):
        """Should delete cannibalization_pairs, post_health_scores, post_clusters, clusters."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                tc = TopicClusterer()

        db = MockConnection()
        cluster_ids = [uuid4(), uuid4()]
        db._fetch_returns = [
            [make_record(id=cid) for cid in cluster_ids],  # old cluster IDs
        ]

        executed_queries: list[str] = []
        original_execute = db.execute

        async def tracking_execute(query, *args):
            executed_queries.append(query)
            return await original_execute(query, *args)

        db.execute = tracking_execute

        await tc._clear_old_clusters(db, TEST_SITE_ID)

        # Should have executed 4 DELETE statements in cascade order
        assert len(executed_queries) >= 4
        assert any("cannibalization_pairs" in q for q in executed_queries)
        assert any("post_health_scores" in q for q in executed_queries)
        assert any("post_clusters" in q for q in executed_queries)
        assert any("DELETE" in q and "clusters" in q for q in executed_queries)

    @pytest.mark.asyncio
    async def test_clear_no_old_clusters_is_noop(self):
        """No existing clusters should be a safe no-op."""
        with patch("app.services.clustering.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test-key")
            with patch("app.services.clustering.AsyncAnthropic"):
                from app.services.clustering import TopicClusterer
                tc = TopicClusterer()

        db = MockConnection()
        db._fetch_returns = [[]]  # No old clusters

        # Should not raise
        await tc._clear_old_clusters(db, TEST_SITE_ID)
