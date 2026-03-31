# Phase 6 — Living Ecosystem: Rivers, Animals, Grass, Weather

Turn the landscape from a static terrain map into a fully alive ecosystem where every visual element maps to a real content metric.

## Architecture

### Backend: New Service `ecosystem_visuals.py`

One service that computes all visual metadata for the landscape. Returns a single payload per site with everything the frontend needs to render rivers, animals, grass, weather, water quality, and terrain features.

```python
class EcosystemVisualsService:
    async def compute_visuals(self, db, site_id) -> dict:
        """Compute all ecosystem visual metadata for a site."""
        return {
            "rivers": [...],          # Internal link flow between clusters
            "grass": {...},           # Per-cluster freshness ground cover
            "weather": {...},         # Per-cluster trend weather effects
            "animals": {...},         # Per-cluster behavior creatures
            "water_quality": {...},   # Per-cluster engagement signals
            "terrain_features": {...} # Structural issues (rocks, bridges, etc.)
        }
```

### Backend: New Endpoint

Add to intelligence router:

```
GET /sites/{site_id}/intelligence/ecosystem-visuals
```

Returns the full visual metadata payload. Frontend calls this alongside clusters to render the enhanced landscape.

### Database

No new tables needed — all computed from existing data:
- `internal_links` → rivers
- `posts.published_at` → grass freshness
- `ga4_metrics` → water quality, animals (bounce, time_on_page)
- `gsc_metrics` → animals (CTR, impressions), weather (trends)
- `post_health_scores` → terrain features

### Frontend: New Renderers

Add to the landscape visualization canvas. Each renders a layer on top of the existing ground + vegetation.

## Detailed Specs

### 1. Rivers — Internal Link Flow

**Data computation (`ecosystem_visuals.py`):**

```python
async def _compute_rivers(self, db, site_id, clusters) -> list[dict]:
    """Compute internal link flow between clusters."""
    rivers = []
    
    # For each pair of clusters, count internal links between their posts
    for i, c1 in enumerate(clusters):
        for c2 in clusters[i+1:]:
            # Get post IDs in each cluster
            c1_post_ids = [get post IDs from post_clusters where cluster_id = c1.id]
            c2_post_ids = [get post IDs from post_clusters where cluster_id = c2.id]
            
            # Count links from c1 posts → c2 posts
            forward_links = await db.fetchval("""
                SELECT COUNT(*) FROM internal_links
                WHERE source_post_id = ANY($1) AND target_post_id = ANY($2)
            """, c1_post_ids, c2_post_ids)
            
            # Count links from c2 posts → c1 posts
            backward_links = await db.fetchval("""
                SELECT COUNT(*) FROM internal_links
                WHERE source_post_id = ANY($1) AND target_post_id = ANY($2)
            """, c2_post_ids, c1_post_ids)
            
            total = forward_links + backward_links
            if total > 0:
                rivers.append({
                    "from_cluster_id": str(c1.id),
                    "to_cluster_id": str(c2.id),
                    "forward_links": forward_links,
                    "backward_links": backward_links,
                    "total_links": total,
                    "bidirectional_ratio": min(forward_links, backward_links) / max(forward_links, backward_links, 1),
                    "width": min(total / 3, 5),  # River width: 1-5 based on link density
                    "quality": "clear"  # Will be enhanced with engagement data
                })
    
    # Also detect dry riverbeds: clusters that SHOULD be linked but aren't
    # (clusters with similar topics but zero links between them)
    
    return rivers
```

**Visual rules:**
- `total_links >= 5` → wide, flowing river with animated water
- `total_links 2-4` → narrow stream
- `total_links 1` → trickle
- `total_links 0` but clusters are adjacent/similar → dry riverbed (cracked grey path)
- `bidirectional_ratio < 0.2` → waterfall effect (one-directional flow)
- River color based on `quality` field (computed from engagement data if available)

**Frontend rendering:**
- Animated bezier curve between cluster centers
- Water particles flowing along the path
- Width proportional to link count
- Dry riverbeds: dashed grey line with crack texture

### 2. Grass — Content Freshness

**Data computation:**

```python
async def _compute_grass(self, db, site_id, clusters) -> dict:
    """Per-cluster freshness ground cover."""
    grass = {}
    for cluster in clusters:
        # Get average last_modified / published_at for posts in cluster
        avg_age = await db.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (NOW() - COALESCE(p.updated_at, p.published_at))))
            FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            WHERE pc.cluster_id = $1
        """, cluster['id'])
        
        days_old = (avg_age or 0) / 86400
        
        if days_old < 90:
            state = "fresh"        # Short, neat, bright green
        elif days_old < 365:
            state = "maintained"   # Medium height, green
        elif days_old < 730:
            state = "overgrown"    # Tall, wild, yellowish
        else:
            state = "dead"         # Brown, dry, flat
        
        grass[str(cluster['id'])] = {
            "state": state,
            "avg_days_old": round(days_old),
            "oldest_post_days": oldest,
            "newest_post_days": newest,
        }
    return grass
```

**Visual rules:**
- `fresh` → short bright green blades, gently swaying
- `maintained` → medium green grass, normal sway
- `overgrown` → tall, wild grass with yellow tips, chaotic sway, some going in different directions
- `dead` → flat brown/grey stubble, no movement, dry patches

**Frontend rendering:**
- Procedural grass blades around the cluster ground edge
- Height, color, and animation speed based on freshness state
- Grass rendered as small lines/curves from the ground perimeter

### 3. Weather — Trend Direction

**Data computation:**

```python
async def _compute_weather(self, db, site_id, clusters) -> dict:
    """Per-cluster weather based on traffic trends."""
    weather = {}
    for cluster in clusters:
        # Get 90-day traffic trend for posts in this cluster
        # Use gsc_metrics or ga4_metrics, compare last 30d vs previous 60d
        recent = await db.fetchval("""
            SELECT COALESCE(SUM(gm.clicks), 0)
            FROM gsc_metrics gm
            JOIN post_clusters pc ON pc.post_id = gm.post_id
            WHERE pc.cluster_id = $1
            AND gm.date >= NOW() - INTERVAL '30 days'
        """, cluster['id'])
        
        previous = await db.fetchval("""
            SELECT COALESCE(SUM(gm.clicks), 0)
            FROM gsc_metrics gm
            JOIN post_clusters pc ON pc.post_id = gm.post_id
            WHERE pc.cluster_id = $1
            AND gm.date >= NOW() - INTERVAL '90 days'
            AND gm.date < NOW() - INTERVAL '30 days'
        """, cluster['id'])
        
        prev_monthly = previous / 2  # 60 days → monthly avg
        
        if prev_monthly == 0 and recent == 0:
            state = "fog"
        elif prev_monthly == 0:
            state = "sunny"
        else:
            change_pct = (recent - prev_monthly) / prev_monthly * 100
            if change_pct > 20:
                state = "sunny"           # Golden glow
            elif change_pct > -5:
                state = "cloudy"          # Gathering clouds
            elif change_pct > -25:
                state = "rain"            # Rain particles
            else:
                state = "storm"           # Lightning flashes
        
        weather[str(cluster['id'])] = {
            "state": state,
            "recent_traffic": recent,
            "previous_traffic": round(prev_monthly),
            "change_percent": round(change_pct, 1) if prev_monthly > 0 else None,
        }
    return weather
```

**Visual rules:**
- `sunny` → warm golden ambient glow above cluster, subtle light rays
- `cloudy` → grey cloud shapes drifting above cluster, dimmed ground
- `rain` → falling rain particles (small blue lines), darker atmosphere
- `storm` → rain + occasional lightning flash (white flash on cluster), rumble shake
- `fog` → thick mist layer obscuring the cluster partially

**Frontend rendering:**
- Weather effects rendered above each cluster
- Cloud shapes: semi-transparent grey ellipses drifting slowly
- Rain: small animated lines falling downward
- Lightning: random white flash that briefly illuminates the cluster
- Sun: golden radial gradient glow from upper corner of cluster
- Fog: thick foggy overlay, cluster details partially obscured

### 4. Animals — User Behavior Signals

**Data computation:**

```python
async def _compute_animals(self, db, site_id, clusters) -> dict:
    """Per-cluster animal population based on behavior metrics."""
    animals = {}
    for cluster in clusters:
        cluster_animals = []
        
        # Birds = high impressions, low CTR
        avg_ctr = await db.fetchval("""
            SELECT AVG(gm.ctr) FROM gsc_metrics gm
            JOIN post_clusters pc ON pc.post_id = gm.post_id
            WHERE pc.cluster_id = $1
        """, cluster['id'])
        
        avg_impressions = await db.fetchval("""
            SELECT AVG(gm.impressions) FROM gsc_metrics gm
            JOIN post_clusters pc ON pc.post_id = gm.post_id
            WHERE pc.cluster_id = $1
        """, cluster['id'])
        
        if avg_ctr is not None and avg_impressions and avg_ctr < 0.02 and avg_impressions > 500:
            bird_count = min(int((0.02 - avg_ctr) * 200), 5)
            cluster_animals.append({
                "type": "birds",
                "count": bird_count,
                "meaning": f"High impressions ({avg_impressions:.0f}/mo) but low CTR ({avg_ctr:.1%})",
            })
        
        # Foxes = high bounce rate (from GA4)
        avg_bounce = await db.fetchval("""
            SELECT AVG(gm.bounce_rate) FROM ga4_metrics gm
            JOIN post_clusters pc ON pc.post_id = gm.post_id
            WHERE pc.cluster_id = $1
        """, cluster['id'])
        
        if avg_bounce is not None and avg_bounce > 0.7:
            fox_count = min(int((avg_bounce - 0.7) * 10), 3)
            cluster_animals.append({
                "type": "foxes",
                "count": fox_count,
                "meaning": f"High bounce rate ({avg_bounce:.0%})",
            })
        
        # Deer = returning visitors (need GA4 user retention data)
        # Approximate: posts with high pageviews per user
        avg_engagement = await db.fetchval("""
            SELECT AVG(gm.avg_session_duration) FROM ga4_metrics gm
            JOIN post_clusters pc ON pc.post_id = gm.post_id
            WHERE pc.cluster_id = $1
        """, cluster['id'])
        
        if avg_engagement and avg_engagement > 180:  # > 3 min avg
            deer_count = min(int(avg_engagement / 120), 3)
            cluster_animals.append({
                "type": "deer",
                "count": deer_count,
                "meaning": f"High engagement ({avg_engagement:.0f}s avg)",
            })
        
        # Bees = backlinks / social shares (if we have the data)
        # For now, approximate with high-traffic + high CTR = popular content
        if avg_ctr and avg_ctr > 0.05 and avg_impressions and avg_impressions > 1000:
            cluster_animals.append({
                "type": "bees",
                "count": 2,
                "meaning": "High visibility and engagement — attracting external attention",
            })
        
        # Vultures = ranking declining (posts losing position)
        declining_posts = await db.fetchval("""
            SELECT COUNT(*) FROM post_health_scores phs
            JOIN post_clusters pc ON pc.post_id = phs.post_id
            WHERE pc.cluster_id = $1 AND phs.trend = 'declining'
        """, cluster['id'])
        
        if declining_posts and declining_posts >= 2:
            cluster_animals.append({
                "type": "vultures",
                "count": min(declining_posts, 3),
                "meaning": f"{declining_posts} posts losing rankings",
            })
        
        animals[str(cluster['id'])] = cluster_animals
    return animals
```

**Animal visual specs:**

**Birds (circling above):**
- Small V-shaped sprites circling above the cluster in a lazy orbit
- Dark silhouettes against the sky
- Orbit radius slightly larger than cluster rx
- Speed: slow, graceful circles

**Foxes (lurking at edges):**
- Small orange/red triangular shapes at the border of the cluster
- Slink back and forth along the ground perimeter
- Occasionally "pounce" (quick dash toward center, then retreat)
- Eyes that glow faintly

**Deer (grazing in forests):**
- Small brown shapes with antler details, standing inside the cluster
- Gentle idle animation: head dips down (grazing), lifts up, looks around
- Only appear in forest/meadow clusters

**Bees (buzzing around meadows):**
- Tiny yellow dots with rapid random movement
- Small golden glow trail
- Zigzag between flowers and trees
- Gentle buzzing visual (slight blur)

**Vultures (circling deserts/dying clusters):**
- Larger than birds, darker silhouettes
- Slow, menacing circles high above
- Slightly tilted flight path

### 5. Water Quality — Engagement Signals

Enhance the rivers computed in step 1 with engagement data:

```python
async def _compute_water_quality(self, db, rivers, clusters) -> list:
    """Enhance river data with engagement-based water quality."""
    for river in rivers:
        # Get avg engagement metrics for posts in both connected clusters
        from_engagement = await _get_cluster_engagement(db, river['from_cluster_id'])
        to_engagement = await _get_cluster_engagement(db, river['to_cluster_id'])
        
        avg_engagement = (from_engagement + to_engagement) / 2
        
        if avg_engagement > 0.7:
            river['quality'] = 'sparkling'   # Clear, bright blue with sparkle particles
        elif avg_engagement > 0.4:
            river['quality'] = 'clear'       # Normal blue
        elif avg_engagement > 0.2:
            river['quality'] = 'murky'       # Brown/muddy
        else:
            river['quality'] = 'toxic'       # Green, sickly
    
    return rivers
```

**Visual rules:**
- `sparkling` → bright blue water with white sparkle particles floating on surface
- `clear` → normal blue, gentle flow animation
- `murky` → brown/dark water, slower flow, no sparkles
- `toxic` → sickly green, bubbling particles, faint toxic glow

### 6. Terrain Features — Structural Issues

```python
async def _compute_terrain_features(self, db, site_id, clusters) -> dict:
    """Detect structural issues and map to terrain features."""
    features = {}
    for cluster in clusters:
        cluster_features = []
        
        # Boulders = broken internal links (404s)
        broken_links = await db.fetchval("""
            SELECT COUNT(*) FROM internal_links il
            JOIN post_clusters pc ON pc.post_id = il.source_post_id
            WHERE pc.cluster_id = $1 AND il.status_code = 404
        """, cluster['id'])
        
        if broken_links and broken_links > 0:
            cluster_features.append({
                "type": "boulders",
                "count": min(broken_links, 5),
                "meaning": f"{broken_links} broken internal links",
            })
        
        # Erosion = thin content (< 500 words)
        thin_posts = await db.fetchval("""
            SELECT COUNT(*) FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            WHERE pc.cluster_id = $1 AND p.word_count < 500
        """, cluster['id'])
        
        if thin_posts and thin_posts > 0:
            cluster_features.append({
                "type": "erosion",
                "count": thin_posts,
                "meaning": f"{thin_posts} thin posts (< 500 words)",
            })
        
        # Mushrooms = near-duplicate content (very high similarity)
        # Use existing cannibalization data where overlap > 0.8
        duplicates = await db.fetchval("""
            SELECT COUNT(*) FROM cannibalization_pairs cp
            WHERE cp.cluster_id = $1 AND cp.overlap_score > 0.8
        """, cluster['id'])
        
        if duplicates and duplicates > 0:
            cluster_features.append({
                "type": "mushrooms",
                "count": min(duplicates * 2, 6),
                "meaning": f"{duplicates} near-duplicate post pairs",
            })
        
        features[str(cluster['id'])] = cluster_features
    return features
```

**Visual specs:**

**Boulders:** Grey/brown rock shapes placed randomly within the cluster, partially blocking river paths. Static, no animation.

**Erosion:** Crumbling edge effect on the cluster ground — jagged border instead of smooth ellipse, with small debris particles falling.

**Mushrooms:** Small mushroom sprites (cap + stem) growing on dead stump posts. Red-spotted caps. Slight wobble animation.

---

## New Pydantic Models (append to schemas.py)

```python
class RiverData(BaseModel):
    from_cluster_id: str
    to_cluster_id: str
    forward_links: int
    backward_links: int
    total_links: int
    bidirectional_ratio: float
    width: float
    quality: str  # sparkling, clear, murky, toxic

class GrassData(BaseModel):
    state: str  # fresh, maintained, overgrown, dead
    avg_days_old: int
    oldest_post_days: int | None = None
    newest_post_days: int | None = None

class WeatherData(BaseModel):
    state: str  # sunny, cloudy, rain, storm, fog
    recent_traffic: int
    previous_traffic: int
    change_percent: float | None = None

class AnimalData(BaseModel):
    type: str  # birds, foxes, deer, bees, vultures
    count: int
    meaning: str

class TerrainFeature(BaseModel):
    type: str  # boulders, erosion, mushrooms
    count: int
    meaning: str

class EcosystemVisualsResponse(BaseModel):
    rivers: list[RiverData]
    grass: dict[str, GrassData]
    weather: dict[str, WeatherData]
    animals: dict[str, list[AnimalData]]
    water_quality_note: str | None = None
    terrain_features: dict[str, list[TerrainFeature]]
```

## Frontend Types (append to types/phase5.ts or create types/phase6.ts)

```typescript
export interface RiverData {
  from_cluster_id: string;
  to_cluster_id: string;
  forward_links: number;
  backward_links: number;
  total_links: number;
  bidirectional_ratio: number;
  width: number;
  quality: 'sparkling' | 'clear' | 'murky' | 'toxic';
}

export interface GrassData {
  state: 'fresh' | 'maintained' | 'overgrown' | 'dead';
  avg_days_old: number;
  oldest_post_days: number | null;
  newest_post_days: number | null;
}

export interface WeatherData {
  state: 'sunny' | 'cloudy' | 'rain' | 'storm' | 'fog';
  recent_traffic: number;
  previous_traffic: number;
  change_percent: number | null;
}

export interface AnimalData {
  type: 'birds' | 'foxes' | 'deer' | 'bees' | 'vultures';
  count: number;
  meaning: string;
}

export interface TerrainFeature {
  type: 'boulders' | 'erosion' | 'mushrooms';
  count: number;
  meaning: string;
}

export interface EcosystemVisualsResponse {
  rivers: RiverData[];
  grass: Record<string, GrassData>;
  weather: Record<string, WeatherData>;
  animals: Record<string, AnimalData[]>;
  water_quality_note: string | null;
  terrain_features: Record<string, TerrainFeature[]>;
}
```

## Frontend Renderers

Create new component files:

```
frontend/src/components/landscape/
├── RiverRenderer.ts        # Animated bezier rivers between clusters
├── GrassRenderer.ts        # Procedural grass blades around cluster edges
├── WeatherRenderer.ts      # Cloud, rain, sun, storm, fog effects per cluster
├── AnimalRenderer.ts       # Animated creature sprites per cluster
├── TerrainFeatureRenderer.ts  # Boulders, erosion, mushrooms
└── WaterParticles.ts       # Water flow particles for rivers
```

Each renderer exports a function that takes the canvas 2D context, cluster positions, visual data, and current time, and draws its layer.

**Rendering order (back to front):**
1. Background (stars, sky)
2. Fog weather (behind everything)
3. Rivers + water particles
4. Cluster grounds + grass
5. Terrain features (boulders, erosion)
6. Vegetation (trees, bushes — existing)
7. Mushrooms (on stumps)
8. Animals (deer, foxes on ground)
9. Weather (clouds, rain, sun above)
10. Animals (birds, vultures, bees in air)
11. Fireflies + floating leaves (existing)
12. Labels + badges (existing)

## Integration

Update `EcosystemCanvas.tsx` (or the canvas-based renderer) to:
1. Fetch `/sites/{site_id}/intelligence/ecosystem-visuals` alongside cluster data
2. Pass visual data to each renderer
3. Each renderer draws its layer in the animation loop

## Migration

No new tables. Add columns to existing if needed:

```sql
-- Add status_code tracking to internal_links (for boulder detection)
ALTER TABLE internal_links ADD COLUMN IF NOT EXISTS status_code INT;

-- Add bounce_rate and avg_session_duration to ga4_metrics (if not present)
ALTER TABLE ga4_metrics ADD COLUMN IF NOT EXISTS bounce_rate FLOAT;
ALTER TABLE ga4_metrics ADD COLUMN IF NOT EXISTS avg_session_duration FLOAT;
```

## Testing

Add to backend tests:
- `test_ecosystem_visuals.py` — test river computation, grass states, weather assignment, animal population logic, terrain feature detection
- Mock data: create clusters with known metrics, verify correct visual assignments

## When Complete

1. All Python files compile clean
2. Frontend builds with zero errors
3. New tests pass
4. Commit: "feat: Phase 6 — living ecosystem (rivers, grass, weather, animals, terrain features)"
5. Run: openclaw system event --text "Done: Phase 6 complete — rivers, grass, weather, animals, terrain features. The ecosystem is alive." --mode now
