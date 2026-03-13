# Phase 7: Interactive Ecosystem Features — Full Spec

## Overview
14 features across 4 tiers that transform the ecosystem visualization from a static map into a "ride or die" interactive tool that drives retention, virality, and utility.

## Build Waves

### Wave 1 — Frontend-Only (Current Demo Enhancement)
These can be built immediately into the Canvas2D demo and later ported to Next.js.

#### 1. Shareable Ecosystem Card
- One-click "Share" button → generates 1200×630 image (LinkedIn/Twitter optimized)
- Includes: landscape snapshot, health score, key stats, "Made with Enough" watermark
- Uses `canvas.toBlob()` → download or copy to clipboard
- Social meta tags for link previews when shared

#### 2. Seasons
- Detect current month → apply seasonal palette:
  - Spring (Mar-May): cherry blossoms, bright greens, flower particles
  - Summer (Jun-Aug): full lush, golden sunlight, butterflies
  - Autumn (Sep-Nov): orange/red/gold leaves, falling leaf particles increase
  - Winter (Dec-Feb): snow on trees, frost, muted palette, snowflakes
- Seasonal trees: leaf colors shift, bare branches in winter for dead_weight
- Toggle: "Current Season" vs manual season selector

#### 3. Creature Level-Up
- Tie creature evolution to cluster health trends:
  - Deer: fawn (health <50) → deer (50-70) → stag with antlers (70+)
  - Bees: single bee (few backlinks) → swarm (moderate) → hive on tree (many)
  - Foxes: thin fox (moderate bounce) → pack of foxes (severe bounce rate)
  - Birds: single bird → flock formation
  - Vultures: circling (declining) → perched (stagnant) → gone (improving)
- Visual progression tied to real metrics
- Tooltip shows evolution stage + what triggers next level

#### 4. Sound Design
- Web Audio API ambient soundscape per biome:
  - Forest: birds chirping, gentle wind, leaves rustling
  - Swamp: frogs, dripping water, muffled sounds
  - Desert: wind howling, sand, silence
  - Meadow: bees buzzing, grass swaying
  - Seedbed: rain, sprouting sounds
- River: water flowing (volume = link count)
- Storm: thunder rumbles, rain
- Creatures: deer footsteps, fox calls, bird songs
- Master volume + mute toggle
- Default: OFF (opt-in, never auto-play)

#### 5. Easter Eggs
- Unicorn 🦄: appears when ALL clusters hit 90+ health
- Phoenix 🔥: appears when any dead cluster revives (desert→forest transition)
- Dragon 🐉: appears when a single pillar post exceeds 10K traffic/mo
- Rainbow: appears after a storm clears (cluster trend reverses from declining→growing)
- Golden deer: appears during a 30+ day health streak
- Each triggers a one-time celebration animation + notification
- "Achievement Unlocked" toast with shareable badge

#### 6. Action Quests
- Quest panel (collapsible sidebar):
  - 🗡️ Swamp Drainer: "Consolidate these 3 posts into one pillar"
  - 🌱 Seed Planter: "Write a new post for this content gap"
  - 🔗 Bridge Builder: "Add 5 internal links between these clusters"
  - 🧹 Cleanup Crew: "Fix 3 broken links in Pricing desert"
  - 🏔️ Peak Climber: "Get any cluster to 90+ health"
- Each quest shows: estimated traffic impact, difficulty, time estimate
- Progress bar per quest
- Completion animation: landscape visibly transforms
- Quest log with completed/active/available

#### 7. Content Planner Overlay
- Toggle button: "Show Opportunities"
- Renders glowing plot markers on the landscape where content gaps exist
- Each plot shows: suggested topic, estimated traffic, difficulty
- Click plot → AI generates content brief (title, outline, target keywords)
- Plots appear as "cleared land with a signpost" visual
- Based on cluster gap analysis from backend

#### 8. Minimap + Search
- Corner minimap showing full ecosystem at small scale
- Current viewport highlighted as a rectangle
- Click minimap to navigate
- Search bar: type post title → camera flies to that tree and highlights it
- Filter toggles: Pillars only / Cannibalized only / Low health only

### Wave 2 — Backend + Frontend (New Services)

#### 9. Time-Lapse / History Playback
**Backend:**
- New service: `ecosystem_snapshots.py`
- Daily cron: snapshot cluster health scores, post counts, traffic, ecosystem score
- Store in `ecosystem_snapshots` table (site_id, snapshot_date, data JSONB)
- API endpoint: `GET /v1/sites/{id}/ecosystem/history?days=90`

**Frontend:**
- Timeline slider at bottom of ecosystem view
- Drag slider → landscape interpolates between historical states
- Trees grow/shrink, biomes shift, rivers widen/narrow
- Play button: auto-animate through history (1 day per second)
- Date label on slider
- "Before/After" split view option

#### 10. Ecosystem Score + Streak
**Backend:**
- Track daily health score in `ecosystem_streaks` table
- Calculate streak: consecutive days of score improvement or maintenance
- API endpoint: `GET /v1/sites/{id}/ecosystem/streak`

**Frontend:**
- Prominent streak counter: "🔥 12-day streak"
- Streak milestones: 7 days (bronze badge), 14 (silver), 30 (gold), 90 (diamond)
- Notification when streak is at risk: "Your health dropped 2 points — take action to keep your streak!"
- Streak history visualization

#### 11. Content Wrapped (Monthly/Quarterly)
**Backend:**
- New service: `content_wrapped.py`
- Monthly aggregation: posts published, health changes, traffic delta, clusters changed, rivers formed/broken
- Generate narrative with Claude: "Your API Integration forest grew 12% this month..."
- Generate shareable card image (server-side Canvas rendering)
- API endpoint: `GET /v1/sites/{id}/wrapped?period=2026-02`
- Email delivery option (integrate with weekly report)

**Frontend:**
- Story-mode presentation (swipe through slides like Instagram stories)
- Animated stats: numbers count up, trees grow
- Shareable card at end with landscape + key stats
- "Share to LinkedIn" / "Share to Twitter" buttons with pre-filled text

#### 12. Weather Forecasts (Predictive)
**Backend:**
- New service: `trend_forecaster.py`
- Analyze: GSC impression trends, competitor SERP movement, content age decay curves
- Claude-powered forecast: "Based on 3 new competitor posts targeting 'API auth', expect ranking pressure in 2-4 weeks"
- Confidence score per forecast
- API endpoint: `GET /v1/sites/{id}/ecosystem/forecast`

**Frontend:**
- Forecast icons above clusters (☀️→⛈️ with transition arrow)
- Click forecast → detail panel with explanation + recommended actions
- 7-day and 30-day forecast views

### Wave 3 — Advanced Features (Need Additional Data Sources)

#### 13. Ecosystem Comparison
**Backend:**
- New service: `competitor_mapper.py`
- Crawl competitor sitemaps → cluster their content → score their ecosystem
- Side-by-side health comparison
- API: `POST /v1/sites/{id}/compare` (accepts competitor URL)

**Frontend:**
- Split-screen: your landscape | their landscape
- Overlay mode: semi-transparent competitor map on yours
- Gap highlights: where they have forests and you have deserts
- "Beat them here" action buttons

#### 14. Competitor Overlay (Ghost Map)
- Builds on #13
- Toggle: show competitor's content structure as faded ghost trees on your map
- Color-coded: green where you're stronger, red where they are
- Click ghost tree → see competitor's post details + your gap

---

## Database Migrations (005_phase7_tables.sql)

```sql
-- Ecosystem snapshots for time-lapse
CREATE TABLE IF NOT EXISTS ecosystem_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    ecosystem_score INTEGER,
    cluster_data JSONB NOT NULL, -- {cluster_id: {health, post_count, traffic, biome}}
    post_data JSONB, -- {post_id: {health, traffic, cluster}}
    river_data JSONB, -- [{from_cluster, to_cluster, link_count}]
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, snapshot_date)
);

-- Streak tracking
CREATE TABLE IF NOT EXISTS ecosystem_streaks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_score INTEGER,
    last_check_date DATE,
    streak_start_date DATE,
    streak_milestones JSONB DEFAULT '[]', -- [{milestone: 7, achieved_at: "2026-03-01"}]
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id)
);

-- Content Wrapped reports
CREATE TABLE IF NOT EXISTS content_wrapped (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    period_type VARCHAR(10) NOT NULL, -- 'monthly' or 'quarterly'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    stats JSONB NOT NULL, -- {posts_published, health_delta, traffic_delta, ...}
    narrative TEXT, -- Claude-generated story
    card_image_url TEXT, -- S3/CDN URL of shareable card
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, period_type, period_start)
);

-- Quest tracking
CREATE TABLE IF NOT EXISTS ecosystem_quests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    quest_type VARCHAR(50) NOT NULL, -- 'swamp_drainer', 'seed_planter', etc.
    title VARCHAR(255) NOT NULL,
    description TEXT,
    target_data JSONB NOT NULL, -- {cluster_id, post_ids, target_metric, ...}
    status VARCHAR(20) DEFAULT 'available', -- available, active, completed, expired
    progress REAL DEFAULT 0, -- 0.0 to 1.0
    estimated_impact JSONB, -- {traffic_delta, health_delta}
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Achievement/Easter egg tracking
CREATE TABLE IF NOT EXISTS ecosystem_achievements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    achievement_type VARCHAR(50) NOT NULL, -- 'unicorn', 'phoenix', 'dragon', etc.
    achieved_at TIMESTAMPTZ DEFAULT NOW(),
    trigger_data JSONB, -- what caused it
    shared BOOLEAN DEFAULT FALSE,
    UNIQUE(site_id, achievement_type)
);

-- Competitor maps
CREATE TABLE IF NOT EXISTS competitor_maps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    competitor_url TEXT NOT NULL,
    competitor_data JSONB, -- {clusters, posts, health_scores, ecosystem_score}
    last_crawled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, competitor_url)
);

CREATE INDEX idx_snapshots_site_date ON ecosystem_snapshots(site_id, snapshot_date);
CREATE INDEX idx_quests_site_status ON ecosystem_quests(site_id, status);
CREATE INDEX idx_wrapped_site_period ON content_wrapped(site_id, period_type, period_start);
```

## New Backend Services

1. `ecosystem_snapshots.py` — daily snapshot cron + history API
2. `streak_tracker.py` — daily score check + streak calculation
3. `content_wrapped.py` — monthly aggregation + Claude narrative + card generation
4. `trend_forecaster.py` — predictive weather using GSC trends + competitor signals
5. `quest_engine.py` — generate quests from ecosystem analysis, track progress
6. `competitor_mapper.py` — crawl + cluster + score competitor content

## New API Endpoints

- `GET /v1/sites/{id}/ecosystem/history` — time-lapse data
- `GET /v1/sites/{id}/ecosystem/streak` — current streak + milestones
- `POST /v1/sites/{id}/ecosystem/streak/check` — daily check-in
- `GET /v1/sites/{id}/wrapped` — get wrapped report
- `POST /v1/sites/{id}/wrapped/generate` — trigger wrapped generation
- `GET /v1/sites/{id}/ecosystem/forecast` — predictive weather
- `GET /v1/sites/{id}/quests` — list quests
- `POST /v1/sites/{id}/quests/{quest_id}/start` — activate a quest
- `POST /v1/sites/{id}/quests/{quest_id}/progress` — update progress
- `GET /v1/sites/{id}/achievements` — list unlocked achievements
- `POST /v1/sites/{id}/compare` — run competitor comparison
- `GET /v1/sites/{id}/competitors` — list mapped competitors

## Estimated Effort

| Wave | Features | Effort |
|------|----------|--------|
| Wave 1 | 1-8 (frontend) | ~3-4 sessions |
| Wave 2 | 9-12 (backend + frontend) | ~3-4 sessions |
| Wave 3 | 13-14 (advanced) | ~2 sessions |

## Priority Order
1. Shareable Card (fastest viral path)
2. Seasons + Creature Level-Up (visual polish, quick wins)
3. Sound Design + Easter Eggs (delight layer)
4. Action Quests + Content Planner (utility)
5. Minimap + Search (navigation)
6. Time-Lapse (retention hook)
7. Streak (gamification)
8. Content Wrapped (viral engine)
9. Weather Forecasts (predictive value)
10. Competitor features (advanced)
