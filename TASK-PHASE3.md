# Phase 3 — Core UI + Landscape Visualization

Build the complete Next.js frontend for Enough. This is the product users see — the landscape visualization, cannibalization map, Oracle, and health dashboard.

## Tech Stack
- **Framework:** Next.js 14 (App Router)
- **Styling:** Tailwind CSS
- **Visualization:** D3.js (landscape + network graph)
- **State:** React hooks + SWR for data fetching
- **Auth:** Supabase Auth (client-side)
- **Icons:** Lucide React
- **Charts:** Recharts (for trend lines in dashboard)

## Project Structure

```
frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout with providers
│   │   ├── page.tsx                # Landing / redirect to dashboard
│   │   ├── globals.css             # Tailwind + custom styles
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx      # Login page
│   │   │   ├── register/page.tsx   # Register page
│   │   │   └── layout.tsx          # Auth layout (centered card)
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx          # Dashboard layout with sidebar nav
│   │   │   ├── page.tsx            # Main dashboard → redirects to landscape
│   │   │   ├── landscape/page.tsx  # THE LANDSCAPE (home screen)
│   │   │   ├── cannibalization/page.tsx  # Cannibalization map
│   │   │   ├── oracle/page.tsx     # Pre-publish oracle
│   │   │   ├── dashboard/page.tsx  # Health dashboard (numbers view)
│   │   │   ├── consolidation/page.tsx    # Consolidation plans list
│   │   │   └── consolidation/[clusterId]/page.tsx  # Consolidation detail
│   │   └── onboarding/
│   │       └── page.tsx            # Onboarding wizard (connect site)
│   ├── components/
│   │   ├── ui/                     # Reusable UI primitives
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Tooltip.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Spinner.tsx
│   │   │   └── ProgressBar.tsx
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx         # Dashboard sidebar navigation
│   │   │   ├── Header.tsx          # Top header with site selector
│   │   │   └── SiteSelector.tsx    # Dropdown to switch between sites
│   │   ├── landscape/
│   │   │   ├── EcosystemCanvas.tsx     # Main D3 landscape visualization
│   │   │   ├── RegionRenderer.tsx      # Renders a single cluster region
│   │   │   ├── VegetationRenderer.tsx  # Renders trees/vines/stumps/seedlings
│   │   │   ├── LandscapeTooltip.tsx    # Hover tooltip for posts
│   │   │   ├── TimelineSlider.tsx      # Scrub through months
│   │   │   └── LegendPanel.tsx         # Legend explaining visual elements
│   │   ├── cannibalization/
│   │   │   ├── NetworkGraph.tsx        # D3 force-directed graph
│   │   │   ├── PairDetailPanel.tsx     # Side panel showing pair details
│   │   │   └── SeverityBadge.tsx       # Colored severity badge
│   │   ├── oracle/
│   │   │   ├── OracleInput.tsx         # Paste draft / enter keyword
│   │   │   ├── VerdictDisplay.tsx      # Visual verdict with illustration
│   │   │   └── SimilarPostsList.tsx    # List of similar existing posts
│   │   ├── dashboard/
│   │   │   ├── HealthScoreCard.tsx     # Big number + trend
│   │   │   ├── EfficiencyRatio.tsx     # Content efficiency ratio display
│   │   │   ├── PostBreakdown.tsx       # Active/passive/cannibal/dead counts
│   │   │   ├── TrendChart.tsx          # Recharts line chart (30/60/90 day)
│   │   │   └── ClusterList.tsx         # Clusters with ecosystem state icons
│   │   └── consolidation/
│   │       ├── PlanCard.tsx            # Consolidation opportunity card
│   │       ├── QuickWinBanner.tsx      # Highlighted top recommendation
│   │       ├── RedirectMap.tsx         # Redirect map table/export
│   │       └── DraftViewer.tsx         # AI-generated draft viewer/editor
│   ├── lib/
│   │   ├── api.ts                  # API client (fetch wrapper with auth)
│   │   ├── supabase.ts             # Supabase client init
│   │   ├── hooks/
│   │   │   ├── useAuth.ts          # Auth hook (login/register/logout/user)
│   │   │   ├── useSite.ts          # Current site context
│   │   │   ├── useSWRFetch.ts      # SWR wrapper with auth headers
│   │   │   └── useApi.ts           # Typed API hooks for each endpoint
│   │   ├── types.ts                # TypeScript types matching backend schemas
│   │   └── constants.ts            # Colors, ecosystem icons, etc.
│   └── providers/
│       ├── AuthProvider.tsx        # Auth context provider
│       └── SiteProvider.tsx        # Current site context provider
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── .env.local.example
```

## Detailed Component Specs

### 1. Root Layout & Providers (`src/app/layout.tsx`)
- Wrap app in AuthProvider → SiteProvider
- Load Inter font from Google Fonts
- Set dark theme by default (dark background: #0a0f1a, text: #e2e8f0)
- Include Tailwind globals

### 2. Auth Pages
- **Login:** Email + password form, "Sign in with Google" button (Supabase OAuth), link to register
- **Register:** Email + password + name form, same Google OAuth button
- Clean centered card design, dark background
- On success: redirect to /onboarding if no sites, or /landscape if sites exist

### 3. Onboarding Wizard (`src/app/onboarding/page.tsx`)
- Step 1: "Add your site" — name, domain, CMS type selector (WordPress / Other)
  - WordPress: enter site URL + optional app password
  - Other: enter sitemap URL
- Step 2: "Connect Google Analytics" — button triggers Google OAuth flow
  - After OAuth, store GA4 property ID + refresh token via API
- Step 3: "Connect Search Console" — same OAuth (shared with GA4)
  - After OAuth, store GSC site URL via API
- Step 4: "Building your ecosystem..." — trigger crawl + analytics sync + embeddings
  - Show progress: "Crawling content... Found 247 posts"
  - Show progress: "Syncing analytics data..."
  - Show progress: "Generating embeddings..."
  - Show progress: "Analyzing your ecosystem..."
  - When all complete: "Your ecosystem is ready!" → button to /landscape
- Each step can be skipped (GA4/GSC optional)
- Progressive: steps appear one at a time as completed

### 4. Dashboard Layout (`src/app/(dashboard)/layout.tsx`)
- Left sidebar (240px, collapsible):
  - Logo "Enough" at top
  - Nav items with icons:
    - 🗺️ Landscape (primary/home)
    - 🕸️ Cannibalization Map
    - 🔮 Oracle
    - 📊 Dashboard
    - 🔧 Consolidation
  - Site selector at bottom of sidebar
  - User menu (avatar, logout) at very bottom
- Main content area with subtle background
- Top bar: current page title + quick actions

### 5. THE LANDSCAPE (`src/app/(dashboard)/landscape/page.tsx`)

**This is the most important page in the product. Spend the most effort here.**

Uses EcosystemCanvas component with D3.js:

**Canvas layout:**
- Full viewport width/height (minus sidebar)
- Dark background (#0a0f1a) with subtle grid/terrain texture
- Each cluster = a region, positioned using a force-directed layout
  - Region size proportional to post_count
  - Regions don't overlap (collision detection)

**Region rendering (RegionRenderer):**
- Each region has a ground plane (rounded rectangle with organic edges)
- Ground color based on ecosystem_state:
  - 🌲 forest: rich dark green (#1a4731)
  - 🪴 swamp: murky brown-green (#2d3a1f)
  - 🏜️ desert: cracked tan (#8b7355)
  - 🌱 seedbed: bright fresh green (#2d5a27)
  - 🌻 meadow: soft green-yellow (#3d6b3d)
- Cluster label floats above region
- Health score badge in corner

**Vegetation rendering (VegetationRenderer):**
Within each region, posts are rendered as vegetation:
- **Pillar post → Large tree:** Tall SVG tree shape. Height scales with traffic. Canopy width scales with keyword coverage. Rich green canopy with trunk.
- **Supporter post → Bush/shrub:** Medium-height rounded green shape. Healthy looking.
- **Competitor post → Tangled vine:** SVG vine/tangle shape in murky colors. More cannibalization = more tangled. Orange-brown colors.
- **Dead weight → Stump:** Short grey stump with no leaves. Cracked ground around it.
- **New post (≤30 days) → Seedling:** Small bright green sprout. Delicate, small.

**Interactions:**
- **Hover any vegetation element:** Tooltip appears showing:
  - Post title
  - URL
  - Traffic (90-day pageviews)
  - Health score
  - Role (pillar/supporter/competitor/dead_weight)
  - Trend arrow (↑ growing, → stable, ↓ declining)
- **Click any region:** Zoom into that cluster. Shows all posts with more detail.
  - Back button to zoom out to full landscape
- **Click any vegetation element:** Opens side panel with full post details + metrics
- **Zoom/pan:** D3 zoom behavior (scroll to zoom, drag to pan)

**Legend panel (LegendPanel):**
- Fixed position bottom-right
- Shows: tree=pillar, bush=supporter, vine=competitor, stump=dead weight, sprout=seedling
- Shows: ground colors for each ecosystem state
- Collapsible

**Data flow:**
1. Page loads → fetch GET /sites/{id}/intelligence/clusters
2. For each cluster → fetch detail (or do it in one batched call)
3. Pass cluster + post data to EcosystemCanvas
4. D3 renders the landscape
5. SWR revalidation keeps data fresh

### 6. Cannibalization Map (`src/app/(dashboard)/cannibalization/page.tsx`)

Uses NetworkGraph component (D3 force-directed):

- **Nodes:** Each post is a circle node
  - Size proportional to traffic
  - Color based on role (green=pillar, blue=supporter, orange=competitor, grey=dead)
  - Label: truncated title (max 30 chars)
- **Edges:** Lines between cannibalizing post pairs
  - Thickness proportional to overlap_score
  - 🔴 Red = critical/high severity
  - 🟠 Orange = medium severity
  - 🟡 Yellow = low severity
  - Green lines for healthy internal links (from internal_links table)
- **Cluster grouping:** Visual clusters (background circles or convex hulls)
- **Click a node:** Highlight all its connections, show post detail panel
- **Click an edge:** Show PairDetailPanel with:
  - Both post titles + URLs
  - Overlap score + severity
  - List of overlapping queries
  - Recommendation: "Merge post B into post A" or "Redirect post B to post A"
- **Filter by severity:** Toolbar at top to filter by critical/high/medium/low
- **Filter by cluster:** Dropdown to focus on one cluster

### 7. Oracle (`src/app/(dashboard)/oracle/page.tsx`)

**Two-step interface:**

**Step 1 — Input (OracleInput):**
- Textarea: "Paste your draft or describe the content you plan to write..."
- Text input: "Target keyword (optional)"
- Big "Analyze" button
- Subtle hint: "The Oracle will check your draft against your entire content ecosystem"

**Step 2 — Verdict (VerdictDisplay):**
After API returns:
- **High confidence (publish):**
  - Green background glow
  - ☀️ Sun icon
  - "Clear skies. This content has room to grow."
  - Confidence bar: green, nearly full
  - Reasoning text from Claude
  - Recommendation action

- **Medium confidence (update):**
  - Yellow/amber background glow
  - 🌧️ Cloud/rain icon
  - "Some overlap detected. Consider updating existing content instead."
  - Confidence bar: yellow, half
  - Reasoning + specific existing post to update

- **Low confidence (skip):**
  - Red background glow
  - 🌊 Flood/underwater icon
  - "This topic is saturated. Publishing will likely cannibalize existing content."
  - Confidence bar: red, low
  - Reasoning + list of competing posts
  - Direct link to consolidation plan if cluster is a swamp

**Similar posts list (SimilarPostsList):**
- Below the verdict
- Table/card list of existing similar posts
- Columns: title, URL, similarity score, ranking position, traffic
- Sorted by relevance
- Click to open post detail

### 8. Health Dashboard (`src/app/(dashboard)/dashboard/page.tsx`)

**Grid layout with cards:**

**Row 1 — Hero metrics (3 cards):**
- Content Health Score: big number (0-100), colored (red→yellow→green), trend line
- Content Efficiency Ratio: percentage, target line at 50%, trend
- Total Posts: number with active/dead breakdown

**Row 2 — Post breakdown (1 wide card):**
- Horizontal stacked bar:
  - 🟢 Active (pillar + supporter)
  - 🔵 Passive
  - 🟠 Cannibalistic (competitor)
  - 🔴 Dead (dead_weight)
- Numbers below each segment

**Row 3 — Trend chart (1 wide card):**
- Recharts area chart showing traffic over time
- 30/60/90 day views (tab selector)
- Overlay: major actions (consolidations) marked as annotations

**Row 4 — Clusters (1 wide card):**
- Table of all clusters
- Columns: ecosystem icon, label, state, post count, health score
- Click row → navigate to cluster detail (landscape zoomed in)
- Sort by: health score, post count, state

### 9. Consolidation (`src/app/(dashboard)/consolidation/page.tsx`)

**Quick Win banner at top:**
- Highlighted card (accent border, subtle glow)
- "This week's Quick Win: Consolidate [cluster label]"
- Shows: estimated traffic recovery, number of posts to merge
- "Start Consolidation" button → links to detail page

**Plans list below:**
- Cards for each consolidation opportunity (non-quick-win)
- Each card shows:
  - Cluster label
  - Priority score bar
  - Pillar post title
  - "X posts to merge, Y to redirect"
  - Estimated traffic recovery
  - "View Plan" button

### 10. Consolidation Detail (`src/app/(dashboard)/consolidation/[clusterId]/page.tsx`)

**Three sections:**

**Section 1 — Plan overview:**
- Pillar post card (title, URL, health score)
- Merge candidates list (title, URL, score, word count)
- Dead weight list (title, URL)
- Estimated metrics: traffic recovery, effort hours

**Section 2 — Redirect Map:**
- Table: old URL → new URL (pillar)
- "Export CSV" button
- "Push to WordPress" button (disabled if not WP, shows tooltip)

**Section 3 — AI Draft:**
- "Generate Consolidated Draft" button → calls POST .../draft
- Loading state: "Claude is writing your consolidated post..."
- When done: markdown rendered in styled container
- "Copy to Clipboard" button
- "Download as Markdown" button
- Note: "Review and edit this draft before publishing. AI-generated content should always be human-verified."

## API Client (`src/lib/api.ts`)

```typescript
// Wrapper around fetch with:
// - Base URL from env (NEXT_PUBLIC_API_URL)
// - Automatic auth header injection (Bearer token from Supabase session)
// - JSON parsing
// - Error handling (throw on non-2xx)
// - TypeScript generics for response types

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function apiFetch<T>(
  path: string,
  options?: RequestInit & { token?: string }
): Promise<T> {
  const { token, ...fetchOptions } = options || {};
  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...fetchOptions?.headers,
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
```

## TypeScript Types (`src/lib/types.ts`)

Mirror all backend Pydantic models as TypeScript interfaces:
- Site, Post, PostDetail, GA4Metric, GSCMetric
- Cluster, ClusterDetail, PostHealth
- CannibalizationPair
- SiteHealth (dashboard data)
- ConsolidationPlan, ConsolidationDetail, ConsolidationDraft, RedirectEntry
- OracleRequest, OracleVerdict, SimilarPost
- PipelineStatus

## Design System / Constants (`src/lib/constants.ts`)

```typescript
export const ECOSYSTEM_COLORS = {
  forest: { bg: '#1a4731', border: '#2d6b4f', label: 'Forest 🌲' },
  swamp: { bg: '#2d3a1f', border: '#4a5a2f', label: 'Swamp 🪴' },
  desert: { bg: '#8b7355', border: '#a6896a', label: 'Desert 🏜️' },
  seedbed: { bg: '#2d5a27', border: '#3d7a34', label: 'Seedbed 🌱' },
  meadow: { bg: '#3d6b3d', border: '#4d8b4d', label: 'Meadow 🌻' },
};

export const ROLE_COLORS = {
  pillar: '#22c55e',      // green
  supporter: '#3b82f6',   // blue
  competitor: '#f97316',   // orange
  dead_weight: '#6b7280',  // grey
};

export const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#6b7280',
};

export const TREND_ICONS = {
  growing: '↑',
  stable: '→',
  declining: '↓',
};
```

## Configuration

`.env.local.example`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Dependencies

```json
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "d3": "^7.9.0",
    "@types/d3": "^7.4.0",
    "swr": "^2.2.0",
    "recharts": "^2.12.0",
    "lucide-react": "^0.400.0",
    "@supabase/supabase-js": "^2.45.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.3.0"
  }
}
```

## Quality Requirements

- All components typed with TypeScript (strict mode)
- No `any` types — use proper interfaces
- Responsive: desktop-first, works at 1024px minimum
- Dark theme throughout — use the color palette consistently
- Loading states for every async operation (skeletons or spinners)
- Error states for every API call (friendly error messages)
- Empty states for first-time users (before data exists)
- All D3 code in useEffect with proper cleanup (remove SVG on unmount)
- SWR for data fetching with proper cache keys and revalidation
- Extract shared UI into components — no duplicated JSX
- Use Tailwind utility classes — no custom CSS except for D3 canvas

## Critical Design Principle

The landscape IS the product. If the landscape looks generic, feels flat, or doesn't immediately communicate "this is alive" — the whole product fails. The trees should feel like trees. The swamp should feel choking. The desert should feel barren. Spend extra effort on the SVG vegetation shapes and the color palette transitions.

## Build Order

1. Package setup (next, tailwind, deps)
2. Design system (constants, UI primitives, layout)
3. Auth (login, register, provider)
4. Onboarding wizard
5. Dashboard layout (sidebar, header, site selector)
6. Health Dashboard (simplest data view — cards + charts)
7. Cannibalization Map (D3 network graph)
8. Oracle (input + verdict display)
9. Consolidation pages
10. **THE LANDSCAPE** (save for last — highest complexity, highest impact)

## When Complete

- Run `npm run build` to verify no TypeScript errors
- Commit with message: "feat: Phase 3 — complete Next.js frontend with landscape visualization, cannibalization map, oracle, health dashboard, consolidation UI"
- Then run: openclaw system event --text "Done: Phase 3 complete — Next.js frontend with D3 landscape visualization, cannibalization map, pre-publish oracle, health dashboard, consolidation plans, onboarding wizard." --mode now
