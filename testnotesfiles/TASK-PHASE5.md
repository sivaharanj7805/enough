# Phase 5 — Retention + Growth Loops

The final phase. Build what keeps users coming back and brings others in: weekly ecosystem reports, impact tracking, steward profile, Stripe payments, and the landing page.

## What Already Exists
- Backend: FastAPI with Phase 1-4 (data, intelligence, UI, actions)
- Frontend: Next.js with 12 routes (landscape, cannibalization, oracle, dashboard, calendar, consolidation, auth, onboarding)
- 15 database tables across 2 migrations

## What to Build

### Backend — New Services

#### 1. `backend/app/services/weekly_report.py` — Weekly Ecosystem Report

Generate a weekly email report summarizing the ecosystem state:

```python
# Generates HTML email content for the Monday morning report
#
# Content structure:
# 1. Headline: "Your Ecosystem This Week"
# 2. Health score change: "Content Health: 24 → 27 (+3)"
# 3. Efficiency ratio change: "Efficiency: 22% → 24% (+2%)"
# 4. Cluster changes: which improved, which declined
# 5. New threats: any new cannibalization pairs detected
# 6. Quick Win of the week: top consolidation opportunity
# 7. CTA: "Log in to see your full landscape"
#
# Methods:
#   generate_report(db, site_id) -> dict  # {subject, html_body, text_body}
#   send_report(db, site_id) -> bool  # Generate + send via email
#   send_all_reports(db) -> int  # Send for all active sites (cron job)
#
# Uses: Resend API (or SMTP fallback) for email delivery
# Store: report_history table (site_id, sent_at, subject, status)
#
# The report should compare current week vs last week:
#   - Fetch current health scores + efficiency ratio
#   - Fetch previous week's snapshot from report_snapshots table
#   - Calculate deltas
#   - Store current snapshot for next week's comparison
```

#### 2. `backend/app/services/impact_tracker.py` — Consolidation Impact Tracking

Track the impact of consolidation actions over time:

```python
# When a consolidation is completed, snapshot the current metrics.
# Then auto-measure at 30, 60, and 90 days.
#
# Methods:
#   start_tracking(db, site_id, cluster_id, consolidated_urls, pillar_url) -> UUID
#     Creates an impact_tracking record with baseline metrics
#
#   check_impact(db, tracking_id) -> dict
#     Compares current metrics to baseline
#     Returns: {
#       tracking_id, cluster_id, pillar_url,
#       baseline_traffic, current_traffic, traffic_change, traffic_change_pct,
#       baseline_avg_position, current_avg_position, position_change,
#       consolidated_urls_count, redirects_working,
#       days_since_consolidation, status (tracking|complete),
#       milestone: "30d"|"60d"|"90d"|null
#     }
#
#   check_all_active(db) -> list[dict]
#     Check all active trackings (for cron job)
#
#   generate_impact_card(db, tracking_id) -> dict
#     Generate a shareable impact summary:
#     "You consolidated 8 posts into 1 on March 15.
#      In 90 days: pillar traffic +47%. Cluster traffic +23%.
#      7 redirects passing authority correctly.
#      Net: +2,100 monthly sessions from fewer posts."
#
# Tables:
#   impact_tracking: id, site_id, cluster_id, pillar_url, consolidated_urls[],
#     baseline_traffic, baseline_avg_position, baseline_date,
#     latest_traffic, latest_avg_position, latest_check_date,
#     traffic_change_pct, status (tracking|complete), created_at
#   
#   impact_snapshots: id, tracking_id, date, traffic, avg_position,
#     redirects_working (int), milestone (30d|60d|90d|null)
```

#### 3. `backend/app/services/steward.py` — Steward Profile

Track personal stats for the content manager:

```python
# Aggregates all actions taken by the user across their sites
#
# Methods:
#   get_profile(db, user_id) -> dict
#     Returns: {
#       user_id, member_since,
#       swamps_cleared: int,  # completed consolidations on swamp clusters
#       deserts_revived: int,  # desert clusters that improved to meadow+
#       seedlings_planted: int,  # new posts tracked in seedbed clusters
#       total_posts_consolidated: int,
#       total_redirects_created: int,
#       estimated_traffic_recovered: int,  # sum of impact tracking results
#       efficiency_improvement: float,  # current efficiency - first efficiency
#       health_improvement: float,  # current health - first health
#     }
#
# No separate table needed — derived from existing data:
#   - Swamps cleared: clusters that were 'swamp' and are now 'forest'/'meadow'
#   - Traffic recovered: sum from impact_tracking
#   - Efficiency improvement: compare first vs latest health dashboard snapshots
```

#### 4. `backend/app/services/stripe_service.py` — Stripe Integration

Handle subscription management:

```python
# Methods:
#   create_checkout_session(user_id, price_id, success_url, cancel_url) -> str
#     Returns Stripe checkout session URL
#
#   handle_webhook(payload, sig_header) -> None
#     Process Stripe webhooks:
#     - checkout.session.completed → activate subscription
#     - customer.subscription.updated → update tier
#     - customer.subscription.deleted → downgrade to free
#     - invoice.payment_failed → flag account
#
#   get_subscription(db, user_id) -> dict | None
#     Returns current subscription details
#
#   check_usage_limits(db, user_id, feature) -> bool
#     Check if user is within their tier limits:
#     - free: 1 site, ≤50 posts, no oracle, no consolidation
#     - growth: 1 site, ≤500 posts, 5 consolidations/month
#     - scale: multiple sites, ≤5000 posts, unlimited
#
# Config:
#   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_GROWTH, STRIPE_PRICE_SCALE
```

### Backend — New Migration

`backend/migrations/003_phase5_tables.sql`:

```sql
-- Weekly report history
CREATE TABLE report_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    status TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'failed', 'skipped')),
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Report snapshots (for week-over-week comparison)
CREATE TABLE report_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    health_score FLOAT,
    efficiency_ratio FLOAT,
    total_posts INTEGER,
    active_posts INTEGER,
    dead_posts INTEGER,
    cannibalistic_posts INTEGER,
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, snapshot_date)
);

-- Impact tracking
CREATE TABLE impact_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    pillar_url TEXT NOT NULL,
    consolidated_urls TEXT[] NOT NULL,
    baseline_traffic INTEGER DEFAULT 0,
    baseline_avg_position FLOAT,
    baseline_date DATE NOT NULL,
    latest_traffic INTEGER,
    latest_avg_position FLOAT,
    latest_check_date DATE,
    traffic_change_pct FLOAT,
    status TEXT DEFAULT 'tracking' CHECK (status IN ('tracking', 'complete')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Impact snapshots (30/60/90 day checkpoints)
CREATE TABLE impact_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracking_id UUID NOT NULL REFERENCES impact_tracking(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    traffic INTEGER DEFAULT 0,
    avg_position FLOAT,
    redirects_working INTEGER DEFAULT 0,
    milestone TEXT CHECK (milestone IN ('30d', '60d', '90d')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Stripe subscription tracking (extends profiles)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'free';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMPTZ;

CREATE INDEX idx_report_history_site ON report_history(site_id);
CREATE INDEX idx_report_snapshots_site_date ON report_snapshots(site_id, snapshot_date);
CREATE INDEX idx_impact_tracking_site ON impact_tracking(site_id);
CREATE INDEX idx_impact_tracking_status ON impact_tracking(status);
CREATE INDEX idx_impact_snapshots_tracking ON impact_snapshots(tracking_id);
```

### Backend — New Router

Create `backend/app/routers/retention.py`:

```
# Weekly Reports
POST /reports/send-weekly
  → Trigger weekly report for a specific site (admin/cron)
GET  /sites/{id}/reports/history
  → List past report history

# Impact Tracking
POST /sites/{id}/impact/track
  → Body: { cluster_id, pillar_url, consolidated_urls[] }
  → Start tracking a consolidation
GET  /sites/{id}/impact
  → List all impact trackings for the site
GET  /sites/{id}/impact/{tracking_id}
  → Detailed impact view with snapshots
POST /sites/{id}/impact/{tracking_id}/check
  → Trigger an impact check (compare current vs baseline)
GET  /sites/{id}/impact/{tracking_id}/card
  → Generate shareable impact card data

# Steward Profile
GET  /profile/steward
  → Get the current user's steward profile

# Stripe
POST /billing/checkout
  → Body: { price_id, success_url, cancel_url }
  → Returns { checkout_url }
GET  /billing/subscription
  → Get current subscription details
POST /billing/webhook
  → Stripe webhook handler (no auth)
GET  /billing/portal
  → Returns { portal_url } for Stripe customer portal
```

### Backend — New Pydantic Models

```python
class ReportHistoryEntry(BaseModel):
    id: UUID
    site_id: UUID
    subject: str
    status: str
    sent_at: datetime

class ImpactTrackingResponse(BaseModel):
    id: UUID
    site_id: UUID
    cluster_id: UUID | None
    pillar_url: str
    consolidated_urls: list[str]
    baseline_traffic: int
    baseline_avg_position: float | None
    baseline_date: str
    latest_traffic: int | None
    latest_avg_position: float | None
    latest_check_date: str | None
    traffic_change_pct: float | None
    status: str
    days_since: int

class ImpactSnapshotResponse(BaseModel):
    snapshot_date: str
    traffic: int
    avg_position: float | None
    redirects_working: int
    milestone: str | None

class ImpactDetailResponse(BaseModel):
    tracking: ImpactTrackingResponse
    snapshots: list[ImpactSnapshotResponse]

class ImpactCardResponse(BaseModel):
    tracking_id: UUID
    headline: str
    pillar_url: str
    days_since: int
    traffic_change: int
    traffic_change_pct: float
    posts_consolidated: int
    redirects_working: int
    summary: str

class StartTrackingRequest(BaseModel):
    cluster_id: UUID | None = None
    pillar_url: str
    consolidated_urls: list[str]

class StewardProfile(BaseModel):
    user_id: str
    member_since: str
    swamps_cleared: int
    deserts_revived: int
    seedlings_planted: int
    total_posts_consolidated: int
    total_redirects_created: int
    estimated_traffic_recovered: int
    efficiency_improvement: float
    health_improvement: float

class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str

class CheckoutResponse(BaseModel):
    checkout_url: str

class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    stripe_subscription_id: str | None
    current_period_end: str | None

class PortalResponse(BaseModel):
    portal_url: str
```

### Frontend — New Pages & Components

#### 1. Impact Tracking Page

Create `frontend/src/app/(dashboard)/impact/page.tsx`:
- List all impact trackings for the current site
- Each tracking card shows:
  - Pillar post title/URL
  - Days since consolidation
  - Traffic change (number + percentage, green/red)
  - Status badge (tracking/complete)
  - "View Details" link
- "Start Tracking" button (opens modal to input pillar URL + consolidated URLs)

Create `frontend/src/app/(dashboard)/impact/[trackingId]/page.tsx`:
- Detailed view of a single consolidation impact
- Timeline showing 30/60/90 day milestones
- Traffic chart (Recharts) showing before/after
- Impact card (shareable summary) with "Copy" and "Download as Image" buttons

Add impact components:
- `frontend/src/components/impact/ImpactCard.tsx` — The shareable card
- `frontend/src/components/impact/ImpactTimeline.tsx` — Milestone timeline
- `frontend/src/components/impact/TrafficChangeChart.tsx` — Before/after chart

#### 2. Steward Profile Page

Create `frontend/src/app/(dashboard)/profile/page.tsx`:
- Personal stats display:
  - Member since
  - Swamps cleared / deserts revived / seedlings planted (with icons)
  - Total posts consolidated
  - Total redirects created
  - Estimated traffic recovered
  - Health + Efficiency improvement (before → after)
- "Export for Performance Review" button → downloads PDF-formatted summary
- Clean, personal, no gamification — just honest accounting

#### 3. Billing Page

Create `frontend/src/app/(dashboard)/billing/page.tsx`:
- Current plan display (Free/Growth/Scale)
- Usage stats (posts used / limit, sites used / limit)
- Plan comparison cards:
  - Free: $0/mo — 1 site, 50 posts, basic landscape
  - Growth: $99/mo — 1 site, 500 posts, full features
  - Scale: $299/mo — multi-site, 5000 posts, unlimited
- "Upgrade" button → Stripe checkout
- "Manage Subscription" button → Stripe portal
- Current billing period + next payment date

#### 4. Landing Page

Create `frontend/src/app/(marketing)/page.tsx` (or update root page):
- Hero section:
  - Headline: "Publish Less. Grow More."
  - Subheadline: "Every content tool tells you to create more. Tended is the only one that tells you when more is less."
  - CTA button: "See Your Ecosystem Free" → /register
  - Static mockup of the landscape visualization
- How it works section (3 steps):
  - Connect → See → Act
  - Each with icon + brief description
- Features section:
  - The Landscape (with screenshot/mockup)
  - Cannibalization Detection
  - Pre-Publish Oracle
  - Consolidation Engine
- Social proof section:
  - Placeholder for impact report screenshots
  - "Helped companies increase traffic 35% by publishing 40% less"
- Pricing section:
  - 3 plan cards (Free/Growth/Scale)
  - Feature comparison
- CTA section:
  - "Your content library is a living ecosystem. Time to see it."
  - Sign up button
- Footer:
  - Links, copyright

#### 5. Sidebar Updates

Add to sidebar navigation:
- 📈 Impact (between Calendar and Consolidation)
- 👤 Profile (at bottom, before logout)
- 💳 Billing (at bottom, before logout)

### Update requirements.txt

Add:
```
stripe==11.4.1
resend==2.5.0
```

### Configuration

Add to `backend/app/config.py`:
```python
# Stripe
stripe_secret_key: str = ""
stripe_webhook_secret: str = ""
stripe_price_growth: str = ""  # Stripe price ID for Growth tier
stripe_price_scale: str = ""   # Stripe price ID for Scale tier

# Email (Resend)
resend_api_key: str = ""
email_from: str = "Tended <reports@tended.app>"
```

Add to `backend/.env.example`:
```
# Stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_GROWTH=
STRIPE_PRICE_SCALE=

# Email (Resend)
RESEND_API_KEY=
EMAIL_FROM=Tended <reports@tended.app>
```

## Quality Requirements

- All new backend code: async, typed, documented, proper error handling + logging
- All new frontend code: TypeScript strict, no `any`, loading/error/empty states
- Frontend types must EXACTLY match backend Pydantic models (field names + nullable)
- `npm run build` must pass with zero errors
- All Python files must compile clean
- Stripe webhook endpoint must NOT require auth (it's called by Stripe)
- Weekly report HTML should be inline-styled (email clients strip <style> tags)
- Landing page should be visually distinct from the dashboard (marketing feel)

## When Complete

1. Verify Python: `find backend -name "*.py" -exec python3 -c "import py_compile; py_compile.compile('{}', doraise=True)" \;`
2. Verify frontend: `cd frontend && npm run build`
3. Commit: "feat: Phase 5 — weekly reports, impact tracking, steward profile, Stripe billing, landing page"
4. Run: openclaw system event --text "Done: Phase 5 complete — weekly ecosystem reports, impact tracking with shareable cards, steward profile, Stripe billing, marketing landing page. TENDED IS SHIP-READY." --mode now
