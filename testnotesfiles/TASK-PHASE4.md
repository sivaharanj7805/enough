# Phase 4 — Action Layer

Build the features that turn Tended's insights into done. This phase adds the Ecosystem Voice narratives, Content Calendar Restraint recommendations, WordPress redirect push, and the full consolidation execution workflow.

## What Already Exists
- Backend: FastAPI with all Phase 1 (data) + Phase 2 (intelligence) services
- Frontend: Next.js with landscape, cannibalization map, oracle, dashboard, consolidation UI
- Services: clustering, cannibalization, health_scoring, consolidation, oracle

## What to Build

### Backend — New Services

#### 1. `backend/app/services/ecosystem_voice.py` — Narrative Generation

Generate Claude-powered narrative summaries per cluster in the voice of the ecosystem:

```python
# For each cluster, generate a 2-4 sentence narrative that describes
# its state using the ecosystem metaphor.
#
# Uses Claude API (AsyncAnthropic, claude-sonnet-4-20250514)
#
# Prompt template per ecosystem state:
# 
# forest: "Describe a thriving, old-growth forest region. The pillar post
#   '{pillar_title}' has stood strong for {age} months. {supporter_count}
#   supporting posts grow in its shade. Use nature metaphors. 2-3 sentences."
#
# swamp: "Describe a choking swamp. {post_count} posts fight for the same
#   sunlight on '{topic}'. The best post is being strangled by its siblings.
#   Use urgent, visceral nature metaphors. 2-3 sentences."
#
# desert: "Describe a barren desert. Posts on '{topic}' haven't been touched
#   since {last_update}. The soil is still good but nothing grows.
#   Use melancholy nature metaphors. 2-3 sentences."
#
# seedbed: "Describe fresh soil with new seedlings. Something was just planted
#   on '{topic}'. It needs time and space to grow. Hopeful tone. 2-3 sentences."
#
# meadow: "Describe a quiet meadow. Content on '{topic}' is modest but stable.
#   Room to grow or decline. Peaceful tone. 2-3 sentences."
#
# Store narratives in a new table: cluster_narratives
#   - cluster_id (FK), narrative_text, generated_at
# Regenerate weekly or on-demand
#
# Methods:
#   generate_for_cluster(db, cluster_id) -> str
#   generate_for_site(db, site_id) -> int (count of narratives generated)
```

#### 2. `backend/app/services/calendar_restraint.py` — Publishing Recommendations

Generate data-backed publishing cadence recommendations per cluster:

```python
# For each cluster, analyze saturation and recommend publishing cadence
#
# Logic:
#   forest → "This cluster is healthy. Recommended: maintain current cadence.
#     Consider 1 supporting post per quarter to keep it fresh."
#   
#   swamp → "This cluster is oversaturated. Recommended: publish NOTHING new
#     for {months} months. Focus on consolidating the top {n} posts instead."
#     months = ceil(cannibalization_rate * 6)
#
#   desert → "This cluster needs revival. Recommended: update the top
#     {n} existing posts first, then add {n} new posts targeting these
#     keyword gaps: {gap_keywords}."
#     gap_keywords = high-impression, low-click queries from GSC
#
#   seedbed → "This cluster is new. Recommended: wait {weeks} weeks
#     before publishing anything else nearby. Let the seedlings take root."
#     weeks = 6-8 depending on early traction signals
#
#   meadow → "This cluster has room to grow. Recommended: {n} new posts
#     this quarter targeting: {suggested_keywords}."
#     suggested_keywords = related queries from GSC with impressions but no clicks
#
# Store in: cluster_recommendations table
#   - cluster_id (FK), recommendation_type (pause|maintain|revive|grow),
#     recommendation_text, suggested_keywords[], pause_months (nullable),
#     generated_at
#
# Also generate site-wide summary:
#   "Your content calendar for the next quarter:
#    - Pause: [cluster labels] (oversaturated)
#    - Maintain: [cluster labels] (healthy)
#    - Revive: [cluster labels] (needs updating)
#    - Grow: [cluster labels] (room for new content)"
#
# Methods:
#   generate_for_site(db, site_id) -> list[dict]
#   get_recommendations(db, site_id) -> list[dict]
```

#### 3. `backend/app/services/redirect_push.py` — WordPress Redirect Push

Push redirect maps directly to WordPress via REST API:

```python
# For WordPress sites, push 301 redirects via the Redirection plugin API
# or by writing to .htaccess via WP REST API
#
# Strategy: Use the popular "Redirection" plugin's REST API if available
# Fallback: Create a simple redirect PHP snippet and push via WP REST API
#
# Methods:
#   check_redirection_plugin(site) -> bool  # Check if plugin is installed
#   push_redirects(db, site_id, redirect_map) -> dict  # Push and return status
#   verify_redirects(site, redirect_map) -> dict  # Verify redirects are active
#
# Each redirect: {old_url: str, new_url: str, type: 301}
# Store push status in: redirect_log table
#   - site_id, old_url, new_url, status (pending|pushed|verified|failed),
#     pushed_at, verified_at, error
```

### Backend — New Migration

`backend/migrations/002_phase4_tables.sql`:

```sql
-- Cluster narratives (ecosystem voice)
CREATE TABLE cluster_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE UNIQUE,
    narrative_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Content calendar recommendations
CREATE TABLE cluster_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE UNIQUE,
    recommendation_type TEXT NOT NULL CHECK (recommendation_type IN ('pause', 'maintain', 'revive', 'grow')),
    recommendation_text TEXT NOT NULL,
    suggested_keywords TEXT[],
    pause_months INTEGER,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Redirect push log
CREATE TABLE redirect_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    old_url TEXT NOT NULL,
    new_url TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'pushed', 'verified', 'failed')),
    pushed_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cluster_narratives_cluster ON cluster_narratives(cluster_id);
CREATE INDEX idx_cluster_recommendations_cluster ON cluster_recommendations(cluster_id);
CREATE INDEX idx_redirect_log_site ON redirect_log(site_id);
```

### Backend — New Router Endpoints

Add to `backend/app/routers/intelligence.py` or create `backend/app/routers/actions.py`:

```
# Ecosystem Voice
GET  /sites/{id}/intelligence/clusters/{cluster_id}/narrative
  → Returns the narrative for a cluster
POST /sites/{id}/intelligence/narratives/generate
  → Generate/refresh narratives for all clusters (background task)

# Content Calendar Restraint  
GET  /sites/{id}/intelligence/calendar
  → Returns all publishing recommendations for the site
POST /sites/{id}/intelligence/calendar/generate
  → Generate/refresh recommendations (background task)

# Redirect Push (WordPress only)
POST /sites/{id}/redirects/push
  → Body: { redirect_map: [{old_url, new_url}] }
  → Push redirects to WordPress
GET  /sites/{id}/redirects/status
  → Check status of pushed redirects
POST /sites/{id}/redirects/verify
  → Verify all pushed redirects are working
```

### Backend — New Pydantic Models

Add to `backend/app/models/schemas.py`:

```python
class ClusterNarrativeResponse(BaseModel):
    cluster_id: UUID
    narrative_text: str
    generated_at: datetime

class CalendarRecommendation(BaseModel):
    cluster_id: UUID
    cluster_label: str | None
    ecosystem_state: str | None
    recommendation_type: str  # pause, maintain, revive, grow
    recommendation_text: str
    suggested_keywords: list[str] | None
    pause_months: int | None

class CalendarResponse(BaseModel):
    site_id: UUID
    recommendations: list[CalendarRecommendation]
    summary: str  # Site-wide calendar summary

class RedirectPushRequest(BaseModel):
    redirect_map: list[RedirectEntry]

class RedirectStatusEntry(BaseModel):
    old_url: str
    new_url: str
    status: str
    pushed_at: datetime | None
    verified_at: datetime | None
    error: str | None

class RedirectStatusResponse(BaseModel):
    site_id: UUID
    entries: list[RedirectStatusEntry]
    total: int
    pushed: int
    verified: int
    failed: int
```

### Frontend — New Components & Pages

#### Ecosystem Voice in Landscape

Update `frontend/src/components/landscape/RegionRenderer.tsx`:
- When a region is clicked/zoomed, show the narrative text below the cluster label
- Fetch from GET /sites/{id}/intelligence/clusters/{cluster_id}/narrative
- Display as styled quote block with appropriate icon per ecosystem state

Create `frontend/src/components/landscape/EcosystemNarrative.tsx`:
- A card component that displays the narrative
- Styled per ecosystem state (forest=calm green, swamp=urgent amber, etc.)
- Shown in the cluster detail view and in the landscape post detail panel

#### Content Calendar Page

Create `frontend/src/app/(dashboard)/calendar/page.tsx`:
- Fetches GET /sites/{id}/intelligence/calendar
- Displays site-wide summary at top
- Groups recommendations by type:
  - 🔴 Pause (don't publish) — shown with warning styling
  - 🟢 Maintain — shown with calm styling  
  - 🟡 Revive (update existing) — shown with action styling
  - 🔵 Grow (publish new) — shown with opportunity styling
- Each recommendation card shows:
  - Cluster label + ecosystem state icon
  - Recommendation text
  - Suggested keywords (if any) as tags
  - Pause duration (if any)
- "Refresh Recommendations" button → POST .../calendar/generate
- "Export to CSV" button → download recommendations as CSV

Add "Calendar" nav item to sidebar (between Dashboard and Consolidation):
- Icon: Calendar from lucide-react
- Route: /calendar

#### Redirect Push UI in Consolidation Detail

Update `frontend/src/components/consolidation/RedirectMap.tsx`:
- "Push to WordPress" button now functional (not just disabled)
- On click: POST /sites/{id}/redirects/push with the redirect map
- Show loading state during push
- After push: show status per redirect (✅ pushed, ❌ failed)
- "Verify Redirects" button → POST .../redirects/verify
- Show verification status (✅ verified, ⏳ pending)
- Keep "Export CSV" working as before

### Update requirements.txt

No new Python dependencies needed (all use existing anthropic, httpx, asyncpg).

## Quality Requirements

- All new backend code: async, typed, documented, proper error handling + logging
- All new frontend code: TypeScript strict, no `any`, loading/error/empty states
- Frontend types must EXACTLY match backend Pydantic models
- Claude API calls use AsyncAnthropic with rate limiting (max 5/second)
- All background tasks log start/completion/failure
- `npm run build` must pass with zero errors

## When Complete

1. Verify all Python files compile: `find . -name "*.py" -exec python3 -c "import py_compile; py_compile.compile('{}', doraise=True)" \;`
2. Verify frontend builds: `cd frontend && npm run build`
3. Commit with: "feat: Phase 4 — ecosystem voice, content calendar, redirect push, action layer complete"
4. Run: openclaw system event --text "Done: Phase 4 action layer complete — ecosystem voice narratives, content calendar restraint, WordPress redirect push, full consolidation workflow." --mode now
