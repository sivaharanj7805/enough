"""Tests for ecosystem visuals — grass, weather, animals, rivers, terrain features."""

import pytest
import pytest_asyncio
from uuid import uuid4

from app.services.ecosystem_visuals import (
    _grass_state,
    _weather_state,
    _river_width,
    EcosystemVisualsService,
)
from tests.conftest import MockConnection, make_record


# ──────────────── Grass State Tests ────────────────


class TestGrassState:
    """Test grass state assignment based on average content age."""

    def test_fresh_under_90_days(self):
        assert _grass_state(0) == "fresh"
        assert _grass_state(30) == "fresh"
        assert _grass_state(89) == "fresh"

    def test_maintained_90_to_365(self):
        assert _grass_state(90) == "maintained"
        assert _grass_state(200) == "maintained"
        assert _grass_state(364) == "maintained"

    def test_overgrown_365_to_730(self):
        assert _grass_state(365) == "overgrown"
        assert _grass_state(500) == "overgrown"
        assert _grass_state(729) == "overgrown"

    def test_dead_over_730(self):
        assert _grass_state(730) == "dead"
        assert _grass_state(1000) == "dead"
        assert _grass_state(2000) == "dead"

    def test_boundary_fresh_maintained(self):
        assert _grass_state(89.9) == "fresh"
        assert _grass_state(90) == "maintained"

    def test_boundary_maintained_overgrown(self):
        assert _grass_state(364.9) == "maintained"
        assert _grass_state(365) == "overgrown"


# ──────────────── Weather State Tests ────────────────


class TestWeatherState:
    """Test weather assignment based on traffic trends."""

    def test_sunny_growth_above_20_pct(self):
        state, pct = _weather_state(130, 100)
        assert state == "sunny"
        assert pct == 30.0

    def test_cloudy_slight_change(self):
        state, pct = _weather_state(100, 100)
        assert state == "cloudy"
        assert pct == 0.0

    def test_rain_moderate_decline(self):
        state, pct = _weather_state(80, 100)
        assert state == "rain"
        assert pct == -20.0

    def test_storm_severe_decline(self):
        state, pct = _weather_state(50, 100)
        assert state == "storm"
        assert pct == -50.0

    def test_fog_no_data(self):
        state, pct = _weather_state(0, 0)
        assert state == "fog"
        assert pct is None

    def test_sunny_from_zero_previous(self):
        state, pct = _weather_state(100, 0)
        assert state == "sunny"
        assert pct is None

    def test_boundary_sunny_cloudy(self):
        # Exactly +20% → should be cloudy (> 20 needed for sunny)
        state, pct = _weather_state(120, 100)
        assert state == "cloudy"  # 20.0 is not > 20

    def test_boundary_cloudy_rain(self):
        # -5% exactly: not > -5, so falls to rain
        state, pct = _weather_state(95, 100)
        assert state == "rain"
        # Just above boundary: still cloudy
        state2, pct2 = _weather_state(96, 100)
        assert state2 == "cloudy"

    def test_boundary_rain_storm(self):
        # -25% exactly: not > -25, so falls to storm
        state, pct = _weather_state(75, 100)
        assert state == "storm"
        # Just above boundary: still rain
        state2, pct2 = _weather_state(76, 100)
        assert state2 == "rain"


# ──────────────── River Width Tests ────────────────


class TestRiverWidth:
    """Test river width calculation from link count."""

    def test_single_link(self):
        assert round(_river_width(1), 2) == 0.33

    def test_small_links(self):
        assert round(_river_width(3), 2) == 1.0

    def test_medium_links(self):
        assert round(_river_width(9), 2) == 3.0

    def test_capped_at_5(self):
        assert _river_width(15) == 5.0
        assert _river_width(100) == 5.0

    def test_zero_links(self):
        assert _river_width(0) == 0.0


# ──────────────── Animal Population Tests ────────────────


class TestAnimalPopulation:
    """Test animal population logic via the service."""

    @pytest.mark.asyncio
    async def test_birds_low_ctr_high_impressions(self):
        """Birds appear when CTR < 0.02 and impressions > 500."""
        db = MockConnection()
        cluster_id = uuid4()

        # avg_ctr, avg_impressions, avg_bounce, avg_engagement, declining_posts
        db._fetchval_returns = [0.01, 1000.0, None, None, 0]

        service = EcosystemVisualsService()
        animals = await service._compute_animals(db, [{"id": cluster_id}])

        result = animals[str(cluster_id)]
        bird_entries = [a for a in result if a["type"] == "birds"]
        assert len(bird_entries) == 1
        assert bird_entries[0]["count"] >= 1

    @pytest.mark.asyncio
    async def test_foxes_high_bounce(self):
        """Foxes appear when bounce_rate > 0.7."""
        db = MockConnection()
        cluster_id = uuid4()

        # avg_ctr, avg_impressions, avg_bounce, avg_engagement, declining_posts
        db._fetchval_returns = [0.05, 200.0, 0.85, None, 0]

        service = EcosystemVisualsService()
        animals = await service._compute_animals(db, [{"id": cluster_id}])

        result = animals[str(cluster_id)]
        fox_entries = [a for a in result if a["type"] == "foxes"]
        assert len(fox_entries) == 1
        assert fox_entries[0]["count"] >= 1

    @pytest.mark.asyncio
    async def test_deer_high_engagement(self):
        """Deer appear when avg_session_duration > 180."""
        db = MockConnection()
        cluster_id = uuid4()

        # avg_ctr, avg_impressions, avg_bounce, avg_engagement, declining_posts
        db._fetchval_returns = [0.05, 200.0, 0.5, 300.0, 0]

        service = EcosystemVisualsService()
        animals = await service._compute_animals(db, [{"id": cluster_id}])

        result = animals[str(cluster_id)]
        deer_entries = [a for a in result if a["type"] == "deer"]
        assert len(deer_entries) == 1
        assert deer_entries[0]["count"] >= 1

    @pytest.mark.asyncio
    async def test_bees_high_ctr_high_impressions(self):
        """Bees appear when CTR > 0.05 and impressions > 1000."""
        db = MockConnection()
        cluster_id = uuid4()

        # avg_ctr, avg_impressions, avg_bounce, avg_engagement, declining_posts
        db._fetchval_returns = [0.08, 1500.0, 0.5, 100.0, 0]

        service = EcosystemVisualsService()
        animals = await service._compute_animals(db, [{"id": cluster_id}])

        result = animals[str(cluster_id)]
        bee_entries = [a for a in result if a["type"] == "bees"]
        assert len(bee_entries) == 1
        assert bee_entries[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_vultures_declining_posts(self):
        """Vultures appear when >= 2 posts are declining."""
        db = MockConnection()
        cluster_id = uuid4()

        # avg_ctr, avg_impressions, avg_bounce, avg_engagement, declining_posts
        db._fetchval_returns = [0.05, 200.0, 0.5, 100.0, 3]

        service = EcosystemVisualsService()
        animals = await service._compute_animals(db, [{"id": cluster_id}])

        result = animals[str(cluster_id)]
        vulture_entries = [a for a in result if a["type"] == "vultures"]
        assert len(vulture_entries) == 1
        assert vulture_entries[0]["count"] == 3

    @pytest.mark.asyncio
    async def test_no_animals_null_data(self):
        """No animals when all metrics are NULL."""
        db = MockConnection()
        cluster_id = uuid4()

        # All None
        db._fetchval_returns = [None, None, None, None, 0]

        service = EcosystemVisualsService()
        animals = await service._compute_animals(db, [{"id": cluster_id}])

        result = animals[str(cluster_id)]
        assert len(result) == 0


# ──────────────── Terrain Feature Tests ────────────────


class TestTerrainFeatures:
    """Test terrain feature detection."""

    @pytest.mark.asyncio
    async def test_boulders_broken_links(self):
        """Boulders appear for broken (404) internal links."""
        db = MockConnection()
        cluster_id = uuid4()

        # broken_links, thin_posts, duplicates
        db._fetchval_returns = [3, 0, 0]

        service = EcosystemVisualsService()
        features = await service._compute_terrain_features(db, [{"id": cluster_id}])

        result = features[str(cluster_id)]
        boulder_entries = [f for f in result if f["type"] == "boulders"]
        assert len(boulder_entries) == 1
        assert boulder_entries[0]["count"] == 3

    @pytest.mark.asyncio
    async def test_erosion_thin_content(self):
        """Erosion appears for posts with < 500 words."""
        db = MockConnection()
        cluster_id = uuid4()

        # broken_links, thin_posts, duplicates
        db._fetchval_returns = [0, 5, 0]

        service = EcosystemVisualsService()
        features = await service._compute_terrain_features(db, [{"id": cluster_id}])

        result = features[str(cluster_id)]
        erosion_entries = [f for f in result if f["type"] == "erosion"]
        assert len(erosion_entries) == 1
        assert erosion_entries[0]["count"] == 5

    @pytest.mark.asyncio
    async def test_mushrooms_near_duplicates(self):
        """Mushrooms appear for near-duplicate pairs (overlap > 0.8)."""
        db = MockConnection()
        cluster_id = uuid4()

        # broken_links, thin_posts, duplicates
        db._fetchval_returns = [0, 0, 2]

        service = EcosystemVisualsService()
        features = await service._compute_terrain_features(db, [{"id": cluster_id}])

        result = features[str(cluster_id)]
        mushroom_entries = [f for f in result if f["type"] == "mushrooms"]
        assert len(mushroom_entries) == 1
        assert mushroom_entries[0]["count"] == 4  # 2 * 2

    @pytest.mark.asyncio
    async def test_no_features_clean_cluster(self):
        """No features for a cluster with no issues."""
        db = MockConnection()
        cluster_id = uuid4()

        db._fetchval_returns = [0, 0, 0]

        service = EcosystemVisualsService()
        features = await service._compute_terrain_features(db, [{"id": cluster_id}])

        result = features[str(cluster_id)]
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_boulders_capped_at_5(self):
        """Boulders count is capped at 5."""
        db = MockConnection()
        cluster_id = uuid4()

        db._fetchval_returns = [10, 0, 0]

        service = EcosystemVisualsService()
        features = await service._compute_terrain_features(db, [{"id": cluster_id}])

        result = features[str(cluster_id)]
        boulder_entries = [f for f in result if f["type"] == "boulders"]
        assert boulder_entries[0]["count"] == 5

    @pytest.mark.asyncio
    async def test_mushrooms_capped_at_6(self):
        """Mushrooms count is capped at 6."""
        db = MockConnection()
        cluster_id = uuid4()

        db._fetchval_returns = [0, 0, 10]

        service = EcosystemVisualsService()
        features = await service._compute_terrain_features(db, [{"id": cluster_id}])

        result = features[str(cluster_id)]
        mushroom_entries = [f for f in result if f["type"] == "mushrooms"]
        assert mushroom_entries[0]["count"] == 6
