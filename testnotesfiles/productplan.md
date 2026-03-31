# Tended — Dashboard Product Specification

**Version:** 1.0 — March 29, 2026
**This document is the single source of truth for the Tended web dashboard.**

---

## PRODUCT OVERVIEW

Tended is a web dashboard where a paying subscriber ($149/month Growth, $349/month Scale) sees their content analyzed, scored, clustered, and receives specific recommendations for every post on their site. The dashboard is the product they're paying for. The PDF audit is the free sample that gets them in the door.

The dashboard must answer one question on every page: **"What should I do next to improve my content?"**

---

## PART 1: ARCHITECTURE

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | TypeScript, React (Next.js or Vite), Tailwind CSS | Dashboard UI |
| Backend | Python, FastAPI, async | API, pipeline orchestration |
| Database | Supabase (PostgreSQL + pgvector) | Posts, embeddings, scores, recommendations |
| Auth | Supabase Auth | Email/password signup, Google OAuth |
| Payments | Stripe | Checkout, subscriptions, webhooks, billing portal |
| Email | Resend | Transactional email, audit PDF delivery |
| Hosting | Fly.io (backend), Vercel (frontend) | Production deployment |
| AI | OpenAI text-embedding-3-small | Embeddings |
| AI | Anthropic Claude Sonnet | Cluster labels, meta descriptions, enrichment |
| PDF | Python (reportlab or weasyprint) | Audit report generation |

### Data Flow

```
User signs up → Supabase Auth creates account
  → User enters payment → Stripe Checkout
    → Webhook fires → subscription tier saved to DB
      → User submits site URL → pipeline triggers
        → Crawl → Embed → Cluster → Readability → PageRank
          → Intent → AI Citability → Health Scoring
            → Cannibalization → Problems → Recommendations
              → Claude Label Backfill
                → Dashboard populates with data
                  → User sees results
```

### API Endpoints the Dashboard Calls

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /auth/register | Create account |
| POST | /auth/login | Sign in |
| GET | /auth/google | Google OAuth redirect |
| GET | /auth/google/callback | OAuth callback |
| POST | /sites | Add a site |
| GET | /sites | List user's sites |
| GET | /sites/{id} | Site details + overall scores |
| DELETE | /sites/{id} | Remove site |
| POST | /sites/{id}/crawl | Trigger re-crawl + full pipeline |
| GET | /sites/{id}/crawl/status | Pipeline progress polling |
| GET | /sites/{id}/posts | List posts (paginated, sortable, filterable) |
| GET | /sites/{id}/posts/{post_id} | Single post with all scores, problems, recommendations |
| GET | /sites/{id}/clusters | List clusters with health + state |
| GET | /sites/{id}/clusters/{id} | Cluster detail with posts |
| GET | /sites/{id}/recommendations | All recommendations (filterable by type, priority) |
| GET | /sites/{id}/cannibalization | All overlap pairs (sortable by overlap score) |
| GET | /sites/{id}/problems | All problems (filterable by type, severity) |
| GET | /sites/{id}/analytics/overview | Aggregate stats (if GA4/GSC connected) |
| POST | /sites/{id}/sync-analytics | Trigger GA4/GSC sync |
| GET | /sites/{id}/health-history | Health score over time (for trend tracking) |
| POST | /audit/generate | Generate PDF audit for a site |
| GET | /billing/portal | Redirect to Stripe billing portal |

### External Service Connections

| Service | Connection Method | What It Provides | When Connected |
|---------|------------------|-----------------|----------------|
| Google Analytics 4 | OAuth2 | Per-URL pageviews, bounce rate, time on page, engagement | Post-signup (optional) |
| Google Search Console | OAuth2 | Per-URL search queries, clicks, impressions, avg position | Post-signup (optional) |
| Stripe | Webhooks + API | Subscription status, plan tier, payment method, billing portal | Signup (required for paid features) |
| Resend | API | Transactional email delivery, audit PDF email | Background (automatic) |

### GA4/GSC Connection Flow

1. User clicks "Connect Google Analytics" in Settings
2. OAuth2 redirect to Google consent screen
3. User grants read-only access to GA4 property
4. Callback stores refresh token in DB
5. Backend syncs last 90 days of per-URL metrics
6. Health scores recalculate with traffic/engagement/ranking factors
7. Dashboard shows updated scores + traffic data
8. Same flow for GSC (separate connection)

**When GA4/GSC is NOT connected:**
- Health scores use crawl-only factors (freshness, depth, links, techseo, AI readiness)
- Dashboard shows a persistent but dismissible banner: "Connect Google Analytics for a complete health score — your current score uses content analysis only"
- All traffic-dependent features show a "Connect GA4 to unlock" state instead of data
- The product is fully functional without GA4/GSC — it's degraded, not broken

---

## PART 2: GLOBAL DESIGN SYSTEM

### Colors

Same system as the PDF report:

| Color | Hex | Use |
|-------|-----|-----|
| Red | #DC2626 | Critical scores (<30), errors, urgent badges |
| Amber | #D97706 | Warning scores (30-55), moderate badges |
| Green | #059669 | Good scores (>55), success states, completed actions |
| Brand Blue | #2563EB | Logo, primary buttons, links, active nav |
| Dark Grey | #111827 | Headers, primary text |
| Body Grey | #374151 | Body text |
| Medium Grey | #6B7280 | Secondary text, labels |
| Light Grey | #9CA3AF | Captions, placeholders, disabled text |
| Border Grey | #E5E7EB | Borders, dividers |
| Background | #F9FAFB | Card backgrounds, sidebar background |
| Page Background | #FFFFFF | Main content area |

### Typography

| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Page title (H1) | 24px | Bold (700) | #111827 |
| Section header (H2) | 18px | Semibold (600) | #111827 |
| Card header (H3) | 16px | Semibold (600) | #111827 |
| Body text | 14px | Regular (400) | #374151 |
| Small text | 13px | Regular (400) | #6B7280 |
| Caption | 12px | Regular (400) | #9CA3AF |
| Metric number (large) | 36px | Bold (700) | Dynamic (red/amber/green) |
| Metric number (medium) | 24px | Bold (700) | Dynamic |
| Badge text | 12px | Medium (500) | White on colored bg |

Font: Inter. Fallback: system sans-serif. Never mix families.

### Score Colors (Applied Everywhere)

Every score in the entire dashboard follows this rule:

| Score Range | Color | Badge Label |
|-------------|-------|-------------|
| 0-29 | #DC2626 (red) | Critical |
| 30-44 | #D97706 (amber) | Below Average |
| 45-59 | #D97706 (amber) | Moderate |
| 60-74 | #059669 (green) | Good |
| 75-100 | #059669 (green) | Excellent |

This applies to: health scores, AI citability scores, E-E-A-T scores, schema scores, extraction scores, cluster health, post scores. No exceptions.

### Components

**Cards:** White background, 1px #E5E7EB border, 8px border-radius, 16px padding. Drop shadow: 0 1px 2px rgba(0,0,0,0.05). Used for every distinct content block.

**Badges:** Pill-shaped (full border-radius), 12px text, 4px 8px padding. Background uses the score color at 10% opacity, text uses the score color at 100%.

**Buttons:**
- Primary: #2563EB background, white text, 8px border-radius
- Secondary: white background, 1px #E5E7EB border, #374151 text
- Danger: #DC2626 background, white text
- Ghost: no background, #2563EB text

**Tables:** Same spec as PDF — horizontal borders only, alternating row backgrounds, dynamic score colors.

**Empty States:** Centered icon (light grey), heading ("No recommendations yet"), subtext explaining why and what to do, primary button CTA. Never show a blank page.

**Loading States:** Skeleton shimmer animation on cards. Never a spinner in the middle of an empty page.

**Error States:** Red border card with error icon, clear message, retry button. Never a raw error code or stack trace.

---

## PART 3: LAYOUT

### Global Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Top Bar (56px height)                                        │
│ ┌─────────┬───────────────────────────────────────┬────────┐ │
│ │ tended. │  Site Selector Dropdown                │ Avatar │ │
│ └─────────┴───────────────────────────────────────┴────────┘ │
├────────────┬────────────────────────────────────────────────┤
│            │                                                │
│  Sidebar   │  Main Content Area                             │
│  (240px)   │  (remaining width, max 1200px centered)        │
│            │                                                │
│  Nav items │  Page Title (H1)                               │
│            │  Page description (optional)                   │
│            │                                                │
│            │  ┌─────────────────────────────────────────┐   │
│            │  │  Content cards, tables, charts           │   │
│            │  │                                          │   │
│            │  └─────────────────────────────────────────┘   │
│            │                                                │
│            │                                                │
├────────────┴────────────────────────────────────────────────┤
│ No footer — dashboard is infinite scroll / paginated         │
└─────────────────────────────────────────────────────────────┘
```

### Top Bar

- Left: "tended." logo in brand blue, clickable → Today page
- Center: Site selector dropdown (shows current domain, click to switch sites or add new site)
- Right: User avatar/initials, click → dropdown menu with Settings, Billing, Logout

### Sidebar Navigation

240px wide. #F9FAFB background. Fixed position (doesn't scroll with content).

**Nav items (top to bottom):**

| Icon | Label | Page | Priority |
|------|-------|------|----------|
| 🏠 | Today | /dashboard | Launch |
| 📊 | Overview | /overview | Launch |
| 💡 | Recommendations | /recommendations | Launch |
| 📁 | Clusters | /clusters | Launch |
| 🔄 | Overlap | /cannibalization | Launch |
| ⚠️ | Issues | /issues | Launch |
| 📝 | Posts | /posts | Launch |
| ⚙️ | Settings | /settings | Launch |
| 💳 | Billing | /billing | Launch |
| --- | --- | --- | --- |
| 🌍 | Landscape | /landscape | Coming Soon |
| 🔮 | Oracle | /oracle | Coming Soon |
| 📋 | Briefs | /briefs | Coming Soon |
| 🏆 | Competitors | /competitors | Coming Soon |
| 📈 | Impact | /impact | Coming Soon |

Active nav item: brand blue text + light blue background (#EFF6FF).
"Coming Soon" items: grey text (#9CA3AF), clicking shows a modal with description + "We'll notify you when this launches."

### Responsive Behavior

- Desktop (>1024px): sidebar visible, full layout
- Tablet (768-1024px): sidebar collapses to icons only (56px wide), expands on hover
- Mobile (<768px): sidebar hidden, hamburger menu in top bar, content full width

---

## PART 4: PAGE-BY-PAGE SPECIFICATION

---

### PAGE: TODAY (/dashboard)

**Purpose:** Answer "what changed since I was last here?" and "what should I do right now?"

**This is the default landing page after login.**

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Today                                        [Re-analyze ↻] │
│ Last analyzed: March 26, 2026 at 2:14 PM                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Health   │  │ AI Ready │  │ Issues   │  │ Recs     │    │
│  │ 54/100   │  │ 72%      │  │ 628      │  │ 461      │    │
│  │ moderate │  │ of posts │  │ found    │  │ pending  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Top 3 Priority Actions                                  │ │
│  │                                                         │ │
│  │ 1. Add Article schema to your top 10 posts    [Do it →] │ │
│  │ 2. Fix "17 SEO Tips" vs "SEO Copywriting"     [Do it →] │ │
│  │ 3. Add internal links to 47 orphan posts      [Do it →] │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ Cluster Health       │  │ Recent Changes               │ │
│  │                      │  │                              │ │
│  │ Technical SEO    60  │  │ No changes since last        │ │
│  │ SEO Tools        57  │  │ analysis. Re-analyze to      │ │
│  │ Content Mktg     56  │  │ check for updates.           │ │
│  │ ...              ... │  │                              │ │
│  │ Dig. Mktg Res.   53  │  │ [Connect GA4 for live       │ │
│  │                      │  │  traffic tracking]           │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### Elements

**Header row:** Page title "Today" (24px bold) + "Re-analyze" button (secondary style). Below: "Last analyzed: [date] at [time]" in 13px #9CA3AF.

**Re-analyze button behavior:**
- Click → triggers POST /sites/{id}/crawl
- Button changes to "Analyzing..." with a spinner
- Progress bar appears below header showing pipeline stages
- When complete: page refreshes with new data, "Last analyzed" updates

**Stat cards row:** Four cards, equal width, in a horizontal row.

| Card | Number | Color | Label |
|------|--------|-------|-------|
| Health | [score]/100 | Dynamic by score value | "Content Health Score" + badge "(moderate)" |
| AI Ready | [pct]% | Green if >60%, amber if 30-60%, red if <30% | "of posts AI-citable" |
| Issues | [count] | Red always | "issues found" |
| Recs | [count] | #374151 (neutral) | "recommendations pending" |

Number is 36px bold. Label is 13px #9CA3AF. Badge is pill-shaped with score color.

**Top 3 Priority Actions card:** White card with header "Top 3 Priority Actions" (16px semibold).

Three rows, each with:
- Priority number (1, 2, 3) in a colored circle (brand blue)
- Action description in 14px #374151
- "Do it →" link in brand blue, right-aligned, clicking navigates to the specific recommendation detail

These are the same top 3 recommendations shown as Quick Wins in the PDF. Generated from recommendation priority data.

**Cluster Health card:** Left half of a two-column layout below the actions.

Mini table showing all clusters sorted by health score descending:
- Cluster name (14px #374151)
- Health score (14px bold, colored by value)
- Tiny bar showing score as a proportion of 100

Clicking a cluster name navigates to /clusters/{id}.

**Recent Changes card:** Right half of the two-column layout.

If GA4/GSC connected: shows posts with the biggest traffic/ranking changes since last analysis.
If NOT connected: shows "Connect Google Analytics for live traffic tracking" with a link to Settings.
If no re-analysis has been done: shows "No changes since last analysis. Re-analyze to check for updates."

#### Today Page Rules
- [ ] Health score color matches the score value
- [ ] All four stat card numbers come from the database
- [ ] Top 3 actions are the same recommendations as the PDF Quick Wins (highest priority)
- [ ] Cluster health scores are sorted descending (highest first)
- [ ] Re-analyze button calls the correct endpoint and shows progress
- [ ] "Last analyzed" timestamp is from the most recent pipeline run

---

### PAGE: OVERVIEW (/overview)

**Purpose:** Complete picture of the site's content health at a glance. The "executive dashboard."

#### Elements

**Health Score Gauge:** Large circular or semicircular gauge showing the score (0-100). Score number in center (48px bold, colored by value). Label below: "Content Health Score." Badge: "(moderate)." Below gauge: "Based on content analysis — connect Google Analytics for a complete score" if no GA4.

**Health Score Bar:** Same horizontal gradient bar as the PDF. ▼ marker at the score position. Shows where the site sits on the Poor → Excellent spectrum.

**AI Readiness Summary Card:** Spider chart (same as PDF but interactive — hover shows exact scores). Four dimension scores in a row below. Clicking navigates to a detailed AI Readiness breakdown.

**Content Profile Card:**
- Total posts: [N]
- Average word count: [N] words
- Average readability: Flesch [N]
- Content freshness: [N]% updated in last 12 months
- Most common content type: [type]

**Issue Summary Card:** Horizontal bar chart showing issue counts by type (same as PDF bar chart but interactive). Clicking a bar navigates to /issues filtered by that type.

**Cluster Summary Card:** All clusters shown as colored cards in a grid. Each card shows:
- Cluster name
- Post count
- Health score (colored)
- Status badge (Healthy/Declining/Growing)
Clicking a card navigates to /clusters/{id}.

**Recommendation Summary Card:** Breakdown by type:
- Optimize: [N] recommendations
- Differentiate: [N]
- Expand: [N]
- Merge: [N]
- Interlink: [N]
Each type is a clickable row that navigates to /recommendations filtered by that type.

#### Overview Page Rules
- [ ] Every number matches the database
- [ ] Health gauge score matches the Today page score
- [ ] Spider chart values match the PDF AI Readiness values
- [ ] All navigation links go to the correct filtered views

---

### PAGE: RECOMMENDATIONS (/recommendations)

**Purpose:** The actionable core. Every specific thing the user should do, prioritized and filterable.

**This is the page that justifies $149/month.** It must feel like a content strategist built a custom action plan.

#### Layout

**Header:** "Recommendations" (24px bold) + "461 recommendations across 149 posts" (14px #9CA3AF).

**Filter bar:** Horizontal row of filter controls:
- Type dropdown: All, Optimize, Differentiate, Expand, Merge, Interlink
- Priority dropdown: All, High, Medium, Low
- Status dropdown: All, Pending, In Progress, Completed
- Search: text field to search by post title
- Sort: Priority (default), Type, Post Score, Alphabetical

**Recommendation list:** Each recommendation is a card:

```
┌─────────────────────────────────────────────────────────────┐
│ [Type Badge]  [Priority Badge]  [Status: Pending ▼]         │
│                                                              │
│ Add meta description: "The Digital Marketing Templates..."   │
│                                                              │
│ This post has no meta description. Search engines show       │
│ random text snippets instead of a compelling summary.        │
│                                                              │
│ Suggested meta: "23 free marketing templates for SEO,        │
│ content, email, and social media. Download keyword           │
│ research sheets, editorial calendars, and outreach scripts." │
│                                                              │
│ Post: The Digital Marketing Templates Library                │
│ Score: 26/100  │  Cluster: Marketing Resource Hubs           │
│                                                              │
│                                    [Mark Complete ✓] [View →]│
└─────────────────────────────────────────────────────────────┘
```

**Card elements:**
- Type badge: colored pill (blue=Optimize, amber=Differentiate, green=Expand, red=Merge, teal=Interlink)
- Priority badge: High (red), Medium (amber), Low (grey)
- Status dropdown: Pending, In Progress, Completed. User can change status. Completed items move to bottom of list and show a green checkmark
- Recommendation title: bold, 16px
- Description: 14px #374151, 2-3 sentences explaining the problem and consequence
- Suggested fix: if applicable (meta descriptions, title rewrites), shown in a light blue (#EFF6FF) box
- Post reference: post title (clickable → post detail), score (colored), cluster name (clickable → cluster)
- Action buttons: "Mark Complete" (changes status), "View" (navigates to post detail)

**Pagination:** 20 recommendations per page. Show total count. "Showing 1-20 of 461."

#### Recommendation Types and What They Show

| Type | What the Card Shows |
|------|-------------------|
| **Optimize** | The specific SEO fix (add meta, fix title, add headings). If meta description: shows suggested meta in blue box. If title: shows current vs suggested title. |
| **Differentiate** | The two overlapping posts by name, their overlap %, and what to do (rewrite one to target a different angle). Links to both posts. |
| **Expand** | The thin post, its word count, the cluster average word count, and specific topics to add. |
| **Merge** | The two near-duplicate posts, their overlap %, which is stronger, and a redirect recommendation. |
| **Interlink** | The orphan post and 2-3 suggested posts to link FROM (most topically relevant posts in the same cluster). |

#### Recommendation Content Quality Rules
- [ ] Every recommendation references a specific post by name
- [ ] Every "Optimize" recommendation with a suggested meta description passes the same EF-1 through EF-5 rules from the PDF spec (no generic phrases, specific to actual content, accurate numbers)
- [ ] Every "Differentiate" recommendation names both posts and their overlap percentage
- [ ] Every "Expand" recommendation shows current word count vs cluster average
- [ ] Every "Interlink" recommendation suggests specific posts to link from (not just "add internal links")
- [ ] Status changes (Pending → Complete) persist in the database
- [ ] Completed recommendations are counted and shown as progress ("23 of 461 completed — 5%")

---

### PAGE: CLUSTERS (/clusters)

**Purpose:** See how content is organized by topic, identify weak clusters, drill into any cluster.

#### Layout

**Header:** "Topic Clusters" (24px bold) + "[N] clusters across [N] posts" (14px #9CA3AF).

**Cluster grid:** Each cluster is a card in a responsive grid (3 columns on desktop, 2 on tablet, 1 on mobile):

```
┌─────────────────────────┐
│ Content Marketing SEO    │
│                          │
│    56/100                │
│    ████████░░  Healthy   │
│                          │
│ 21 posts                 │
│ 3 overlapping pairs      │
│ 12 recommendations       │
│                          │
│               [View →]   │
└─────────────────────────┘
```

**Card elements:**
- Cluster name: 16px semibold
- Health score: 24px bold, colored by value
- Progress bar: showing score as filled portion (green/amber/red fill)
- Status badge: "Healthy" (green), "Declining" (red), "Growing" (teal)
- Post count, overlap pair count, recommendation count in 13px #6B7280
- "View" link → navigates to cluster detail

**Sort options:** By health (ascending = worst first), by post count, alphabetical.

#### Cluster Detail Page (/clusters/{id})

**Header:** Cluster name (24px bold) + health score (colored) + status badge.

**Sections:**

1. **Cluster Stats Card:** Post count, average word count, average readability, health score, AI citability average, overlap pairs within this cluster.

2. **Posts Table:** All posts in this cluster:
   - Post title (clickable → post detail)
   - Health score (colored)
   - Word count
   - Last updated date
   - Issues count
   - Rec count
   Sortable by any column. Default sort: health ascending (worst first).

3. **Overlap Pairs Card:** Pairs within this cluster:
   - Post A, Post B, Overlap %
   - Resolution recommendation
   Clickable rows → expand to show detail.

4. **Cluster Recommendations Card:** All recommendations for posts in this cluster, same card format as the main Recommendations page but filtered to this cluster.

---

### PAGE: OVERLAP (/cannibalization)

**Purpose:** See all content overlap pairs, understand which posts compete, take action.

#### Layout

**Header:** "Content Overlap" (24px bold) + "[N] pairs involving [N] posts" (14px #9CA3AF).

**Summary stats row:**
- Total pairs: [N]
- Posts involved: [N] of [total] ([pct]%)
- Average overlap: [N]%
- Pairs needing action (>85%): [N]

**Pairs table:** Full table of all overlap pairs, sortable:

| Post A | Post B | Overlap | Severity | Resolution | Action |
|--------|--------|---------|----------|------------|--------|
| [title] | [title] | 89% (red) | High | Differentiate | [Fix →] |
| [title] | [title] | 87% (red) | High | Differentiate | [Fix →] |
| ... | ... | ... | ... | ... | ... |

**Column details:**
- Post A / Post B: clickable titles → post detail
- Overlap: percentage, colored (red >85%, dark amber 83-85%, amber <83%)
- Severity: badge (Critical, High, Medium, Low)
- Resolution: what to do (Redirect, Merge, Differentiate, Monitor)
- Action: "Fix →" button → navigates to the specific recommendation for this pair

**Expandable rows:** Clicking a row expands to show:
- Why these posts overlap (shared topic words, similar headings)
- Which post is stronger (higher health score, more internal links)
- Specific recommendation text

#### Overlap Page Rules
- [ ] All pairs are from the blended overlap score (cosine + title topic), not raw cosine alone
- [ ] No false positives (product reviews of different products, same-format different-topic posts)
- [ ] Overlap percentages match the database values
- [ ] "Posts involved" count is the DISTINCT count of posts appearing in any pair

---

### PAGE: ISSUES (/issues)

**Purpose:** See all content problems by type and severity, prioritize what to fix.

#### Layout

**Header:** "Issues" (24px bold) + "[N] issues across [N] posts" (14px #9CA3AF).

**Issue type summary:** Horizontal cards or tabs showing each issue type with count:

| Type | Count | Severity |
|------|-------|----------|
| Missing meta description | [N] | Medium |
| Orphan posts | [N] | High |
| Thin content | [N] | High |
| Title too long/short | [N] | Medium |
| No headings | [N] | Medium |
| No schema markup | [N] | Medium |
| Low AI citability | [N] | Medium |
| Weak E-E-A-T | [N] | Low |
| Hard to read | [N] | Low |
| No images | [N] | Low |

Clicking a type filters the list below.

**Issues list:** Table of all issues:
- Post title (clickable → post detail)
- Issue type (badge)
- Severity (badge: High red, Medium amber, Low grey)
- Description (consequence-focused: "no internal links — invisible to crawlers")
- Quick fix (if available: "Add a link from [suggested post]")

**Filter bar:** Filter by issue type, severity, cluster. Sort by severity (default), post score, alphabetical.

---

### PAGE: POSTS (/posts)

**Purpose:** Browse every post with its scores, issues, and recommendations.

#### Layout

**Header:** "All Posts" (24px bold) + "[N] posts analyzed" (14px #9CA3AF).

**Filter bar:** Search by title, filter by cluster, filter by health range (0-30, 30-60, 60-100), sort by health/word count/date/title.

**Posts table:**

| Post Title | Score | Cluster | Words | Updated | Issues | Recs |
|-----------|-------|---------|-------|---------|--------|------|
| [title] | 26 (red) | Marketing Hubs | 312 | 2024-01 | 9 | 4 |
| [title] | 54 (amber) | Technical SEO | 3,400 | 2025-11 | 2 | 3 |
| [title] | 71 (green) | Content Mktg | 5,200 | 2026-02 | 1 | 1 |

All columns sortable. Score is colored by value. Clicking a row navigates to post detail.

**Pagination:** 25 posts per page.

#### Post Detail Page (/posts/{id})

**Header:** Post title (24px bold) + health score (colored badge) + "View on site →" external link.

**Sections:**

1. **Score Breakdown Card:** Visual breakdown of all health factors:
   - Freshness: [score]/100 (with last-updated date)
   - Content Depth: [score]/100 (with word count + cluster average)
   - Internal Links: [score]/100 (with inbound link count)
   - Technical SEO: [score]/100 (with checklist of what passes/fails)
   - AI Readiness: [score]/100 (with the four AI dimensions)
   Each factor shown as a horizontal bar with the score and the weight it carries in the composite.

2. **AI Readiness Card:** Mini spider chart for this specific post. Four dimension scores. "Why this post scores [N]/100" with specific explanations.

3. **Issues Card:** All problems for this post listed with severity badges and consequences.

4. **Recommendations Card:** All recommendations for this post with suggested fixes. If meta description is missing: shows the AI-generated suggestion in a blue box with a "Copy" button.

5. **Overlap Card:** If this post appears in any overlap pairs, shows the pairs with the other post title, overlap %, and resolution.

6. **Content Preview Card:** First 500 characters of the post body text. Word count, readability score, heading count, image count, internal link count. All at a glance.

---

### PAGE: SETTINGS (/settings)

**Purpose:** Site configuration, data connections, account management.

#### Sections

1. **Site Information:**
   - Domain: [domain] (read-only)
   - Sitemap URL: [url] (editable)
   - Last crawled: [date]
   - Posts found: [N]
   - [Re-crawl Site] button

2. **Connections:**
   - Google Analytics 4: [Connected ✓] or [Connect GA4 →]
   - Google Search Console: [Connected ✓] or [Connect GSC →]
   - If connected: shows last sync date + [Sync Now] button + [Disconnect] link

3. **Notifications:**
   - Email me when: analysis complete, health score drops >5 points, new issues detected
   - Toggle switches for each

4. **Data:**
   - [Export All Data as CSV] — downloads posts, scores, recommendations, pairs
   - [Generate PDF Report] — generates and downloads the audit PDF
   - [Delete Site Data] — danger button, confirmation modal

5. **Account:**
   - Email: [email]
   - [Change Password]
   - [Delete Account] — danger button, confirmation modal

---

### PAGE: BILLING (/billing)

**Purpose:** Subscription management.

#### Sections

1. **Current Plan Card:**
   - Plan name: Growth ($149/month) or Scale ($349/month)
   - Status: Active / Past Due / Cancelled
   - Next billing date: [date]
   - [Manage Subscription →] — redirects to Stripe billing portal

2. **Plan Comparison:**
   - Growth ($149/month): 1 site, 500 posts, all recommendations, AI content briefs, progress tracking
   - Scale ($349/month): 3 sites, 2,000 posts, white-label reports, priority support
   - [Upgrade] or [Downgrade] buttons as appropriate

3. **Usage:**
   - Posts analyzed: [N] of [limit]
   - Sites: [N] of [limit]
   - Progress bar showing usage toward limit

4. **Billing History:**
   - Table of past invoices with date, amount, status, [Download PDF] link
   - Powered by Stripe billing portal

---

### COMING SOON PAGES

These pages show a consistent "Coming Soon" state:

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│                    [Feature illustration]                     │
│                                                              │
│              Content Landscape                               │
│              Coming Soon                                     │
│                                                              │
│     See your content as a living ecosystem.                  │
│     Healthy clusters are forests. Declining                  │
│     clusters are deserts. Watch your content                 │
│     grow as you fix issues.                                  │
│                                                              │
│              [Notify me when it launches]                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Coming Soon pages:**

| Page | Name | Description |
|------|------|-------------|
| Landscape | Content Landscape | "See your content as a living ecosystem. Healthy clusters are forests. Declining clusters are deserts. Watch your content grow as you fix issues." |
| Oracle | Content Oracle | "Ask questions about your content in plain English. 'Which posts should I update first?' 'What topics am I missing?' Powered by AI." |
| Briefs | Content Briefs | "AI-generated writing briefs for new posts and updates. Includes target keywords, outline, word count targets, and competitive analysis." |
| Competitors | Competitor Analysis | "See how your content health compares to competitors. Benchmark AI readiness, content depth, and topic coverage." |
| Impact | Impact Tracking | "Connect Google Analytics to track the real-world impact of every fix you make. See traffic changes, ranking improvements, and ROI." |

Each page stores email if user clicks "Notify me" — for future launch announcements.

---

## PART 5: ONBOARDING FLOW

### First-Time User Flow

1. **Signup page:** Email + password. Google OAuth button. "Start your free analysis" CTA. No credit card required for signup (but required before full access).

2. **Email confirmation:** Resend sends confirmation email. User clicks link → redirected to onboarding.

3. **Onboarding step 1 — Add your site:**
   - Input field: "Enter your website URL"
   - Example placeholder: "example.com"
   - [Analyze My Site →] button
   - System auto-detects sitemap at /sitemap.xml, /sitemap_index.xml

4. **Onboarding step 2 — Pipeline running:**
   - Progress screen showing pipeline stages with checkmarks:
     - ☐ Crawling pages...
     - ☐ Analyzing content...
     - ☐ Clustering topics...
     - ☐ Scoring health...
     - ☐ Detecting overlap...
     - ☐ Generating recommendations...
   - Each stage checks off as it completes
   - Estimated time remaining shown
   - "This usually takes 2-5 minutes for most sites"

5. **Onboarding step 3 — Results preview:**
   - Shows health score (large, colored), post count, issue count, top finding
   - "Your site scored 54/100. We found 628 issues and generated 461 recommendations."
   - [Subscribe to see all recommendations →] — redirects to Stripe checkout
   - [Download free audit PDF →] — generates and downloads the PDF report (teaser)

6. **After payment:**
   - Stripe checkout completes
   - Webhook updates subscription tier
   - Redirect to /dashboard (Today page) with full data

### Returning User Flow

1. User visits tended.app → redirected to /dashboard if logged in
2. Today page shows latest data
3. If subscription expired: banner "Your subscription has expired. [Resubscribe →]"
4. If subscription past due: banner "Payment failed. [Update payment method →]"

---

## PART 6: ERROR STATES AND EDGE CASES

### Pipeline Failures

If the pipeline fails mid-way:
- Progress screen shows which stage failed with a red ✗
- Error message in plain language: "We couldn't find a sitemap at [domain]/sitemap.xml. Does your site have a sitemap?"
- [Try Again] button
- [Contact Support] link
- User is NEVER left on a spinner that never stops. Maximum timeout: 10 minutes, then show error.

### Common Error Messages

| Situation | Message |
|-----------|---------|
| No sitemap found | "We couldn't find a sitemap at [domain]/sitemap.xml. Make sure your site has a sitemap and try again." |
| Site blocks crawler | "Your site blocked our crawler. You may need to whitelist our user agent. Contact support for help." |
| Empty sitemap | "Your sitemap was found but contains no URLs. Check that your sitemap is properly configured." |
| Too many posts (>5000) | "Your site has [N] posts. We currently support up to [limit] posts on your plan. Upgrade to Scale for larger sites." |
| Pipeline timeout | "Analysis took longer than expected. This can happen with very large sites. We'll email you when it's complete." |
| Stripe payment failed | "Payment failed. Please update your payment method to continue using Tended." |
| GA4 connection failed | "We couldn't connect to Google Analytics. Please try again or check that you granted the correct permissions." |

### Empty States

Every page has a designed empty state for when there's no data:

| Page | Empty State |
|------|-------------|
| Today (no site) | "Add your first site to get started" + [Add Site] button |
| Recommendations (all completed) | "You've completed all recommendations! Re-analyze to find new improvements." + [Re-analyze] button |
| Overlap (no pairs) | "No content overlap detected. Your topics are well-differentiated." |
| Issues (no issues) | "No issues found. Your content is in great shape." + green checkmark |
| Clusters (no clusters) | "Clusters will appear after your site is analyzed." |

---

## PART 7: WHAT THE DASHBOARD DOES NOT DO (FOR NOW)

These features are explicitly out of scope for launch. They are not broken — they are intentionally absent. Adding "Coming Soon" states for each prevents the dashboard from looking incomplete.

| Feature | Why Not Now | When |
|---------|-----------|------|
| Content Landscape (ecosystem visualization) | PixiJS untested in production, needs real user feedback on utility | After 5 paying customers |
| Oracle (AI Q&A) | Needs Claude integration for on-demand queries, cost management | After GA4/GSC integration |
| Content Briefs | Output quality unverified, needs user testing | After 10 paying customers |
| Competitor Analysis | Requires crawling competitor sites, significant infrastructure | After product-market fit |
| Impact Tracking | Requires GA4/GSC connection + historical data | After GA4/GSC integration |
| White-label Reports | Needs PDF template customization (logo, colors) | Scale plan launch |
| Team Collaboration | Multi-user access, roles, comments | After first enterprise customer |
| Slack/Email Notifications | Webhook integrations for alerts | After core dashboard stable |
| API Access | Public API for integrations | After v2 |

---

## PART 8: LAUNCH CHECKLIST

Before the dashboard goes live:

### Authentication
- [ ] Signup with email/password works end-to-end
- [ ] Email confirmation sends and verifies
- [ ] Login works and redirects to /dashboard
- [ ] Google OAuth works (optional — email/password is sufficient for launch)
- [ ] Password reset flow works
- [ ] Logged-out users are redirected to login

### Payments
- [ ] Stripe checkout creates subscription correctly
- [ ] Webhook processes checkout.session.completed and updates DB
- [ ] User tier (Growth/Scale) is enforced (post limits, site limits)
- [ ] Billing portal link works for managing subscription
- [ ] Cancellation flow works (user can cancel, access continues until period end)
- [ ] Failed payment shows clear error with link to update payment method

### Pipeline
- [ ] Submitting a site URL triggers the pipeline
- [ ] Progress polling shows real-time stage updates
- [ ] Pipeline completes within 5 minutes for a 200-post site
- [ ] All data appears in the dashboard when pipeline finishes
- [ ] Error states show clear messages for common failures (no sitemap, blocked crawler, timeout)
- [ ] Re-analyze button triggers a fresh pipeline run

### Dashboard Pages (verify each with real data)
- [ ] Today: stat cards show correct numbers, top 3 actions are relevant
- [ ] Overview: health gauge, spider chart, issue chart all render correctly
- [ ] Recommendations: list loads, filters work, status changes persist
- [ ] Clusters: grid renders, detail page shows posts and pairs
- [ ] Overlap: table loads, overlap percentages are correct, expandable rows work
- [ ] Issues: list loads, filters work, severity badges are colored correctly
- [ ] Posts: table loads, sorting works, detail page shows all scores
- [ ] Settings: site info displays, re-crawl works, GA4/GSC connect buttons present
- [ ] Billing: current plan shows, Stripe portal link works

### Coming Soon Pages
- [ ] Each Coming Soon page renders the designed empty state
- [ ] "Notify me" button stores email
- [ ] Nav items for Coming Soon pages are visually distinct (grey, not active blue)

### Performance
- [ ] Dashboard loads in <2 seconds on broadband
- [ ] Tables with 500+ rows paginate without lag
- [ ] Spider chart renders correctly
- [ ] No console errors on any page

### Mobile
- [ ] All pages are usable on mobile (768px width)
- [ ] Sidebar collapses on tablet, hidden on mobile
- [ ] Tables scroll horizontally on small screens
- [ ] Stat cards stack vertically on mobile

---

## PART 9: SUCCESS METRICS

After launch, track these to know if the dashboard is working:

| Metric | Target | How to Measure |
|--------|--------|---------------|
| Signup → pipeline run | >80% | Users who sign up and submit a site |
| Pipeline run → checkout | >30% | Users who see results and subscribe |
| Day 1 → Day 7 return | >60% | Users who come back within a week |
| Recommendations completed | >10% in first month | Status changes from Pending to Complete |
| Average session duration | >5 minutes | Analytics |
| Pages per session | >4 | Analytics |
| Churn rate (monthly) | <8% | Stripe subscription data |
| NPS score | >40 | In-app survey after 30 days |

---

This is the complete dashboard specification. Every page, every component, every connection, every state. Build it from this document.

# Tended Dashboard Spec — Review & Pipeline Mapping

**Rating: 82/100**
The spec is thorough on layout, design system, and page structure. The gaps are in the connection points between pipeline data and dashboard elements, several UX flows that will break on real data, and missing edge cases that the first 5 customers will hit.

---

## PIPELINE → DASHBOARD MAPPING

Every pipeline step produces data. Every dashboard element consumes data. Here's the complete mapping — and where the connections are broken or missing.

### Step 1: Crawl → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Post title, URL, word count | `posts` | Posts page table, post detail, recommendation cards | ✓ Connected |
| Publish date, modified date | `posts` | Post detail (freshness), "Last updated" in tables | ✓ Connected |
| Meta description | `posts` | Recommendation cards (shows current vs suggested) | ✓ Connected |
| Headings (JSON array) | `posts.headings` | Post detail (heading count), Issues page | ✓ Connected |
| Body HTML | `posts.body_html` | Post detail content preview (first 500 chars) | ✓ Connected |
| Internal links | `internal_links` | Post detail (inbound link count), Interlink recs | ✓ Connected |
| Page type | `posts.page_type` | **NOT consumed anywhere in dashboard spec** | ⚠️ Gap |
| eeat_metadata | `posts.eeat_metadata` | Post detail (tech SEO checklist passes/fails) | ✓ Connected |
| Content hash | `posts.content_hash` | Not displayed — used internally for dedup | ✓ OK |

**Gap: Page type is never shown.** The dashboard should display page type (blog/landing/documentation/glossary/product) in the Posts table as a filterable column. Content marketers want to filter by "show me only blog posts" or "show me only documentation pages." Also, the PIPELINE-01 fix (exclude landing pages from analysis) means some posts in the DB won't have health scores — the dashboard needs to handle this gracefully.

### Step 2: Embeddings → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Post embeddings (1536-dim) | `post_embeddings` | Not directly displayed — used by cannibalization and orphan link recs | ✓ OK |
| Embedding cost | Pipeline logs | Not displayed | ✓ OK |

**No gaps.** Embeddings are infrastructure, not user-facing.

### Step 3: Readability → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Flesch Reading Ease | `posts.readability_score` | Post detail, Content Profile, Issues page (readability_too_complex) | ✓ Connected |
| Grade level | `posts.grade_level` | **NOT consumed anywhere** | ⚠️ Gap |

**Gap: Grade level is computed but never displayed.** It's more intuitive than Flesch scores for most content marketers. "This post reads at a college level" is clearer than "Flesch 49." Show it alongside the Flesch score on the post detail page: "Readability: Flesch 49 (Grade 11 — college level)."

### Step 4: PageRank → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| PageRank score | `posts.pagerank_score` | **NOT consumed anywhere in dashboard spec** | ⚠️ Gap |
| Inbound link count | `internal_links` (counted) | Post detail (internal links factor) | ✓ Connected |

**Gap: PageRank is computed but never surfaced.** The "Internal Authority" ranking from the pipeline is valuable — it shows which posts are the most linked-to on the site. Add a "Top 10 by Internal Authority" card to the Overview page, or add PageRank as a sortable column in the Posts table. Content marketers understand "this post is your most-linked internal page" even if they don't understand PageRank math.

### Step 5: Intent Classification → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Content intent | `posts.content_intent` | **NOT consumed anywhere in dashboard spec** | ⚠️ Gap |

**Gap: Intent is computed, used by cannibalization detection, but never shown to the user.** Add it as a filterable column in the Posts table and as a badge on post detail. Content marketers care about intent — "show me all my commercial posts" or "show me all my informational posts" are real queries. Also, the Overlap page should show intent for each post in a pair — it explains why two topically similar posts are or aren't cannibalizing ("same topic, different intent → not competing").

### Step 6a: Clustering → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Cluster assignments | `post_clusters` | Clusters page grid, post detail cluster reference | ✓ Connected |
| Cluster post count | `clusters.post_count` | Cluster cards, Today page | ✓ Connected |
| Silhouette score | `clusters.silhouette_score` | **NOT consumed anywhere** | OK — internal quality metric |
| UMAP 2D positions | `post_clusters.umap_x/y` | **NOT consumed — explicitly deferred to Landscape page** | ✓ OK (Coming Soon) |

**No critical gaps.** Silhouette score is an internal quality metric that doesn't need user exposure. UMAP positions are correctly deferred to the Landscape (Coming Soon) page.

### Step 6b: TF-IDF Labels → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Cluster label | `clusters.label` | Cluster cards, sidebar cluster health, post detail, recommendation cards | ✓ Connected |

**No gaps.** Labels flow through correctly. The label quality improvements (bigram validation, Claude labels for cold outreach) mean the dashboard will show clean labels.

### Step 6c: AI Citability → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Citability score | `post_health_scores.ai_citability_score` | Post detail AI Readiness card, Overview spider chart | ✓ Connected |
| E-E-A-T score | `post_health_scores.eeat_score` | Post detail AI Readiness card, Overview spider chart | ✓ Connected |
| Schema score | `post_health_scores.schema_score` | Post detail AI Readiness card, Overview spider chart | ✓ Connected |
| Extraction score | `post_health_scores.extraction_score` | Post detail AI Readiness card, Overview spider chart | ✓ Connected |
| AI signals (JSONB) | `post_health_scores.ai_signals` | **NOT consumed — contains per-signal detail** | ⚠️ Missed opportunity |

**Missed opportunity: The `ai_signals` JSONB contains the raw signal counts** (numbered_list_items, statistics_count, definition_count, question_headers, first_person_markers, etc.) that explain WHY a post scored what it scored. The Post Detail AI Readiness card says "Why this post scores [N]/100" but the spec doesn't specify what data drives that explanation. The answer is `ai_signals`. Show a breakdown: "This post has 0 data tables, 0 statistics, 1 definition, 0 question headers → low citability." This is the "prescription" that makes the score actionable.

### Step 7: Health Scoring → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Composite score | `post_health_scores.composite_score` | Everywhere — Today, Overview, Posts, Clusters, Recommendations | ✓ Connected |
| Per-factor scores | `post_health_scores.*_score` | Post detail score breakdown card | ✓ Connected |
| Role (pillar/supporter/etc) | `post_health_scores.role` | **NOT consumed anywhere in dashboard spec** | ⚠️ Gap |
| Score confidence | `post_health_scores.score_confidence` | **NOT consumed anywhere** | ⚠️ Gap |
| Cluster health | `clusters.health_score` | Cluster cards, Today page cluster health | ✓ Connected |
| Ecosystem state | `clusters.ecosystem_state` | Cluster cards status badge | ✓ Connected |
| Trend label | `post_health_scores.trend` | **NOT consumed anywhere** | ⚠️ Gap |

**Gap: Role is never shown.** The pipeline assigns every post a role (pillar, supporter, at_risk, dead_weight, competitor). This is valuable information for content strategists. "Pillar" posts are the ones to protect and build around. "Dead weight" posts are candidates for deletion or consolidation. Add a role badge to the Posts table and make it filterable. On the Cluster detail page, show the role distribution: "8 pillars, 35 supporters, 3 at-risk, 2 dead weight."

**Gap: Score confidence is never shown.** Posts scored with GA4+GSC have "full" confidence. Crawl-only posts have "crawl_only" confidence. The user should know that their scores would change (and improve in accuracy) if they connect GA4/GSC. Show confidence as a subtle indicator on the post detail score breakdown: "Score confidence: Content analysis only. Connect GA4/GSC for traffic-weighted scoring."

**Gap: Trend label is never shown.** Each post has a trend (growing/stable/declining/dead/unknown). In crawl-only mode all are "unknown," but with GA4 connected this becomes valuable. Show it as an arrow icon next to the health score: ↑ growing, → stable, ↓ declining.

### Step 8: Cannibalization → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Post pairs | `cannibalization_pairs` | Overlap page table, Cluster detail overlap card | ✓ Connected |
| Cosine similarity | `cannibalization_pairs.cosine_similarity` | **NOT directly shown — blended score shown instead** | ✓ OK |
| Blended score | `cannibalization_pairs.overlap_score` | Overlap page "Similarity" column | ✓ Connected |
| Severity | `cannibalization_pairs.severity` | Overlap page severity badge | ✓ Connected |
| Resolution | `cannibalization_pairs.resolution` | Overlap page resolution column | ✓ Connected |
| Stronger post | `cannibalization_pairs.stronger_post_id` | **NOT shown in the Overlap page spec** | ⚠️ Gap |
| Shared GSC queries | `cannibalization_pairs.overlapping_queries` | **NOT shown anywhere** | ⚠️ Gap |

**Gap: Stronger post is computed but not shown.** When the resolution is "merge" or "redirect," the user needs to know WHICH post to keep. The pipeline computes this (higher health score + traffic). The Overlap page expandable row should show: "Keep: [stronger post title] (score: 67) → Redirect: [weaker post title] (score: 41) to the keeper."

**Gap: Shared GSC queries are stored but not shown.** When GSC is connected, these are the actual Google queries both posts rank for — the proof of cannibalization. Show them in the expandable row: "Both posts rank for: 'link building tips', 'how to build backlinks', 'backlink strategies'."

### Step 8b: Chunk Confirmation → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Chunk confirmation | `cannibalization_pairs.chunk_overlap_confirmed` | **NOT shown anywhere** | ⚠️ Missed opportunity |
| Chunk similarity | `cannibalization_pairs.chunk_similarity` | **NOT shown anywhere** | ⚠️ Missed opportunity |

**Missed opportunity:** Chunk confirmation adds credibility to the cannibalization finding. "Section-level overlap confirmed" is stronger than just "56% similar." Add a small badge to confirmed pairs on the Overlap page: "Confirmed at section level ✓" vs "Post-level similarity only."

### Step 9: Problem Detection → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Problem type + severity | `content_problems` | Issues page, post detail issues card | ✓ Connected |
| Problem details (JSONB) | `content_problems.details` | **Partially consumed — some fields shown, some not** | ⚠️ Partial |

**Partial gap:** The problem `details` JSON contains specifics like `months_stale`, `word_count`, `cluster_avg`, `readability_score`, etc. The Issues page shows the problem type and severity but the spec doesn't specify how `details` drives the issue description. Be explicit: for `thin_below_cluster_avg`, the description should say "This post has {word_count} words, {pct}% below the cluster average of {cluster_avg} words." Pull these values from `details`, don't hardcode.

### Step 10: Recommendations → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| Recommendation type + priority | `recommendations` | Recommendations page list | ✓ Connected |
| Title + summary + actions | `recommendations` | Recommendation cards | ✓ Connected |
| Status (pending/completed) | `recommendations.status` | Recommendation cards, progress tracking | ✓ Connected |
| Effort estimate | `recommendations.estimated_effort_hours` | **NOT shown in recommendation cards** | ⚠️ Gap |
| Confidence | `recommendations.confidence` | **NOT shown in recommendation cards** | ⚠️ Gap |

**Gap: Effort estimate is computed but not shown.** Every recommendation has an effort estimate (0.25h for meta description, 2.0h for content expansion, 3.0h for merge). Show it on the card: "Estimated effort: 30 min." This helps the user prioritize — they'll do the 15-minute fixes first.

**Gap: Confidence is not shown.** Recommendations have confidence levels (high for objective issues like missing meta, low for subjective suggestions). Show as a subtle indicator so users can distinguish "definitely fix this" from "consider fixing this."

### Step 10b: Claude Enrichment → Dashboard

| Pipeline Output | DB Table | Dashboard Consumer | Status |
|----------------|----------|-------------------|--------|
| AI guidance (JSON) | `recommendations.specific_actions` | Recommendation card expanded view | ✓ Connected |
| Original template actions | `recommendations.specific_actions.original_actions` | Fallback when AI guidance is malformed | ✓ Connected |

**No gaps.** The spec correctly describes showing AI guidance in recommendation cards. The "Get AI Analysis" button for on-demand enrichment is implied but not explicitly specified — add it to the recommendation card spec for unenriched recommendations.

---

## CRITIQUES

### Critique 1: The Today page "Top 3 Priority Actions" won't match the PDF Quick Wins

The spec says: "These are the same top 3 recommendations shown as Quick Wins in the PDF." But the PDF Quick Wins are hardcoded in the PDF generation logic (schema, cannibalization, freshness) while the Today page pulls from the recommendation priority sort. If the recommendation priority sort puts "add_schema" recs first (because they're all high priority), the Today page might show 3 schema recs while the PDF shows schema + cannibalization + freshness.

**Fix:** The Today page should use the same Quick Win selection logic as the PDF — pick the top recommendation from each of 3 different categories (AI readiness, cannibalization, freshness/content) rather than the top 3 by raw priority. Reuse the PDF's Quick Win selection code.

### Critique 2: The Overlap page shows "Overlap %" but the column is labeled "Similarity"

The spec's Overlap page table says the column header is "Overlap" in one place and references "Similarity" in the cannibalization pair data. The PDF uses "Similarity." Pick one and use it everywhere. "Similarity" is more intuitive.

Also, the spec says overlap percentages are colored "red >85%, dark amber 83-85%, amber <83%." But the blended scores from the pipeline range from 0.35 to 0.80 — no pair will ever show >85% because the blended score is much lower than raw cosine. The color thresholds need to match the actual blended score distribution: red >0.55 (high severity), amber 0.40-0.55 (medium), grey <0.40 (monitor). Or if you're displaying the blended score as a percentage (×100), adjust accordingly.

### Critique 3: The Recommendations page doesn't show site-level recs

The pipeline generates 4 site-level recommendations ("126 of 145 posts are missing meta descriptions — start with your top 10 by health score"). These are the most impactful recs because they summarize patterns across the whole site. But the Recommendations page spec shows only per-post recommendation cards. Site-level recs don't have a `post_id` — they're site-wide.

**Fix:** Add a "Site-Wide Actions" section at the top of the Recommendations page, above the per-post list. Show the 4 site-level recs as larger cards with the aggregate stat and the "start with your top 10" guidance. These should be the first things the user sees when they open Recommendations.

### Critique 4: The health score factor weights aren't shown to the user

The Post Detail score breakdown card shows each factor's score but not its weight. The user sees "AI Readiness: 40/100" and "Technical SEO: 75/100" but doesn't know that AI Readiness contributes 28% of the composite while Technical SEO only contributes 7%. Without weights, a user might focus on improving Technical SEO (small impact) instead of AI Readiness (large impact).

**Fix:** Show weights alongside each factor in the score breakdown: "AI Readiness: 40/100 (28% weight) | Technical SEO: 75/100 (7% weight)." Or show it as the weighted contribution: "AI Readiness contributes 11.2 of your 54 total points."

### Critique 5: No "before/after" on re-analysis

The spec describes the re-analyze flow but doesn't specify what happens when the new scores come back. Does the user see that their health score went from 54 to 58? Does the dashboard show which recommendations they completed that caused the improvement?

This is the retention hook. "You fixed 12 issues and your health score improved by 4 points" keeps users coming back. Without it, re-analysis just replaces the old data with new data and the user has no sense of progress.

**Fix:** Add a "Changes Since Last Analysis" card to the Today page (replacing or enhancing the "Recent Changes" card). Show:
- Health score change: 54 → 58 (+4)
- Issues resolved: 12 (of 628)
- Recommendations completed: 23 (of 461)
- New issues found: 3
- Clusters that changed state: "Technical SEO: Declining → Moderate"

Store the previous run's scores in `health_score_history` (the table already exists) and compute diffs on the Today page.

### Critique 6: The onboarding flow shows results before payment — but the results ARE the product

Step 5 of the onboarding shows: "Your site scored 54/100. We found 628 issues and generated 461 recommendations." Then asks for payment to see the recommendations. But the user just saw the health score, issue count, and rec count for free. What more do they need?

The problem: the free preview shows too much (makes the user feel they already got value) or too little (doesn't motivate payment). The spec says to offer a PDF download as a teaser, which is smart — the PDF gives specific findings but gates the full recommendation list.

**Fix:** The onboarding results preview should show:
- Health score (specific number)
- Top 3 findings (same as PDF Key Findings)
- "We generated 85 recommendations — here are 3 examples" (show 3 teaser recs with actions blurred/truncated)
- [Subscribe to see all 85 →]
- [Download free audit PDF →]

The 3 teaser recs with blurred actions create "I can almost see the answer" urgency.

### Critique 7: No mention of rate limiting or abuse prevention

The spec describes the pipeline trigger but doesn't address: what if a user clicks "Re-analyze" 50 times? What if a Growth plan user tries to analyze a 5,000-post site? What if someone signs up, runs the pipeline, downloads the PDF, and cancels within the 30-day guarantee?

**Fix:** Add rate limiting rules:
- Re-analyze: max 1 per 24 hours per site (show countdown timer)
- Pipeline: enforce post limit per plan tier (500 Growth, 2000 Scale) — show a clear error if exceeded
- PDF generation: max 3 per day (prevents scraping)
- Free onboarding run: 1 per account (prevents creating accounts to generate free audits)

### Critique 8: The Settings page "Export All Data as CSV" is underspecified

What does the CSV contain? One file or multiple? How are recommendations formatted? How are cannibalization pairs represented?

**Fix:** Export as a ZIP with multiple CSVs:
- `posts.csv` — all posts with health scores, AI scores, word count, readability, intent, cluster, role
- `recommendations.csv` — all recs with type, priority, status, effort, post title
- `problems.csv` — all problems with type, severity, post title
- `cannibalization_pairs.csv` — all pairs with post titles, similarity, severity, resolution
- `clusters.csv` — all clusters with label, health, state, post count

### Critique 9: The spec doesn't address what happens when crawl-only vs full-data modes produce different scores

When a user first signs up, they get crawl-only scores (6 factors, AI readiness at 28% weight). When they connect GA4/GSC, scores recalculate with 8 factors (traffic at 20%, ranking at 18%). Their health score WILL change — potentially significantly. A post scoring 60 in crawl-only mode might score 40 with real traffic data (because it gets zero visits).

**Fix:** When GA4/GSC is first connected and scores recalculate:
- Show a one-time notification: "Your scores have been updated with traffic and ranking data. Some scores changed significantly — this is expected. Your new scores are more accurate."
- On the Today page "Changes Since Last Analysis" card, distinguish between score changes from content updates vs score changes from new data sources
- Consider showing both scores temporarily: "Content score: 60 | Full score (with traffic): 42"

### Critique 10: The Coming Soon pages are good but the "Content Landscape" is the most urgent

The ecosystem visualization (forest/desert/swamp/meadow) is the product's visual identity. It's the thing that makes screenshots shareable. It's mentioned in the brand doc, it's what the name "Tended" refers to, and it's the most requested feature customers will expect from the brand promise.

The spec defers it to "after 5 paying customers." That's reasonable for engineering prioritization but the brand promise implies it exists. If the DM says "we'll show you your content ecosystem" and the dashboard shows a plain table, that's a disconnect.

**Fix:** For launch, add minimal ecosystem visual cues to the existing Clusters page:
- Green tree icon 🌲 next to "Strong" clusters
- Brown/orange icon 🏜️ next to "Needs Attention" clusters  
- Grey icon next to "Moderate" clusters
This takes 30 minutes and fulfills the brand promise at a minimal level without building the full PixiJS visualization. Then build the full Landscape page after the first 5 customers.

---

## MISSING FROM THE SPEC

### Missing 1: Webhook for pipeline completion

The spec describes polling for pipeline progress (`GET /sites/{id}/crawl/status`) but doesn't mention what happens when the pipeline finishes and the user isn't watching. If the user submits a site and closes the tab, how do they know it's done?

**Fix:** Send a Resend email when the pipeline completes: "Your content analysis for zapier.com is ready. Health score: 60/100. We found 268 issues and generated 85 recommendations. [View your results →]"

### Missing 2: Multi-site experience for Scale plan

The Scale plan allows 3 sites. The spec shows a "Site Selector Dropdown" in the top bar but doesn't detail the multi-site experience. Questions:
- Does the Today page show stats for all sites or just the selected one?
- Is there a cross-site comparison view?
- Can the user see which of their 3 sites needs the most attention?

**Fix:** For launch, keep it simple — the site selector switches context and all pages show data for the selected site only. Add a "All Sites" option to the selector that shows a summary card for each site (health score, issue count, last analyzed date). This is enough for 3 sites.

### Missing 3: What the "Do it →" button on recommendations actually does

The Today page shows "Do it →" next to each priority action. The Recommendations page shows "Mark Complete ✓" and "View →". But what does "Do it" actually mean? For a meta description recommendation, does it copy the suggestion to clipboard? For a merge recommendation, does it show the merge plan? For an interlink recommendation, does it show the specific posts to link from?

**Fix:** "Do it →" navigates to the recommendation's detail view, which shows the full context (problem, consequence, specific actions, AI guidance if enriched). For recommendations with a concrete deliverable (meta description, title suggestion), add a "Copy to clipboard" button. For complex recommendations (merge, differentiate), show the step-by-step plan from the Claude enrichment.

### Missing 4: Health score history chart

The spec mentions `health_score_history` table and a `/sites/{id}/health-history` endpoint, and the Overview page mentions it should exist, but there's no detailed spec for what the history chart looks like.

**Fix:** Add to Overview page: a line chart showing health score over time (one data point per pipeline run). X-axis: dates. Y-axis: 0-100. Color the line by the score color (red/amber/green segments). This is the simplest retention visualization — users want to see their score going up over time.

### Missing 5: Notification system for score drops

The Settings page mentions "Email me when health score drops >5 points" but there's no spec for how this is computed or delivered.

**Fix:** After each pipeline run, compare the new health score with the previous one from `health_score_history`. If the delta exceeds the user's threshold, send a Resend email: "Your content health score dropped from 60 to 54. 3 new issues were detected. [View changes →]"

---

## IMPLEMENTATION PRIORITY

What to build first, second, and third — based on what the first paying customer actually needs vs what can wait.

### Launch (Week 1-2): The minimum that justifies $149/month

| Page | Priority | Why |
|------|----------|-----|
| Auth (signup/login) | Must have | Can't get in without it |
| Onboarding (site submission + pipeline progress) | Must have | First experience |
| Today | Must have | Landing page after login |
| Recommendations | Must have | This IS the product |
| Settings (re-analyze + site info) | Must have | Core functionality |
| Billing (Stripe portal link) | Must have | Payment management |

That's 6 pages. The rest can wait.

### Week 3-4: Complete the core experience

| Page | Priority | Why |
|------|----------|-----|
| Clusters | High | Content strategists want to see topic organization |
| Posts | High | Browse all content with scores |
| Issues | High | See all problems by type |
| Overlap | High | See all cannibalization pairs |
| Overview | Medium | Nice executive summary but Today page covers the basics |

### Month 2: Retention features

| Feature | Priority | Why |
|---------|----------|-----|
| GA4/GSC OAuth | High | Unlocks full-data scoring, the biggest value upgrade |
| Health history chart | High | Shows progress over time — retention hook |
| Score change notifications | Medium | Re-engagement mechanism |
| Pipeline completion email | Medium | User doesn't have to watch the progress bar |
| Post detail page (full) | Medium | Deep dive into individual post scores |

### Month 3+: Differentiation features

| Feature | Priority | Why |
|---------|----------|-----|
| Content Landscape visualization | High | Brand promise fulfillment |
| Export to CSV | Medium | Enterprise customers expect it |
| Content Oracle (AI Q&A) | Low | Nice to have, not retention-critical |
| Content Briefs | Low | Requires validation of output quality |

---

## THE HONEST ASSESSMENT

### What's strong (why 82/100):
- The design system is consistent and professional — score colors, typography, component specs are all well-defined
- Every page has a clear purpose statement ("Answer: what should I do next?")
- Empty states, loading states, and error states are specified for every page — this prevents the "blank page" problem that kills first impressions
- The onboarding flow is well-structured with clear progress indicators
- The Coming Soon pages with "Notify me" are a smart way to handle incomplete features without looking broken
- The responsive breakpoints are specified
- Success metrics are defined with specific targets

### What needs work (the 18-point deduction):
- Pipeline data that's computed but never shown to the user (role, intent, PageRank, grade level, trend, effort estimate, confidence, stronger post, shared queries, chunk confirmation, ai_signals detail) — that's 12 computed fields going to waste (-5)
- Site-level recommendations have no display spec (-2)
- No before/after diff on re-analysis — the retention hook is missing (-3)
- Overlap page color thresholds don't match the actual blended score range (-1)
- Rate limiting and abuse prevention not specified (-2)
- Multi-site experience for Scale plan not detailed (-1)
- Pipeline-to-dashboard connection points not explicitly mapped (-2)
- The "Do it →" action is undefined (-1)
- Health history chart unspecified despite the endpoint existing (-1)

### The single most important thing to get right:
The Recommendations page. It's the product. Everything else (Today, Overview, Clusters, Issues) is navigation to help the user find the right recommendation. If the Recommendations page is fast, filterable, shows specific actions with effort estimates, and lets users track completion — the product works. If it's slow, generic, or hard to navigate — nothing else matters.

Build the Recommendations page first. Make it excellent. Then build everything else around it.

---

## PART 10: FRONTEND RENDERING GAPS — COMPLETE AUDIT

**Audited:** March 29, 2026
**Method:** Line-by-line comparison of every dashboard page against this spec + backend API responses

---

### CRITICAL — Blocks core value proposition

#### GAP-01: Posts list health/role/cluster columns always show "--"
**File:** `frontend/src/app/(dashboard)/posts/page.tsx` line 124-132
**Bug:** The `postMetaMap` useMemo that builds per-post health scores, roles, and cluster names has an empty body. The comment says "We'll build from clusters data" but the logic was never implemented. Every row shows "--" for Health, Role, and Cluster.
**Fix:** Populate `postMetaMap` by iterating `useClusters` → `useClusterDetail` for each cluster, building a map of `post_id → { score, role, clusterId, clusterLabel }`. OR add a bulk backend endpoint `GET /sites/{id}/posts/health` that returns all post health scores in one call.
**Data source:** `useClusters` + `useClusterDetail` (both exist) or new bulk endpoint
**Complexity:** Large (requires either N+1 cluster detail fetches or a new backend endpoint)

#### GAP-02: Overview page missing AI Readiness, Issue Summary, Recommendation Summary, Cluster grid
**File:** `frontend/src/app/(dashboard)/overview/page.tsx`
**Bug:** The spec requires: AI readiness spider chart (4 axes), issue summary bar chart (by type), recommendation summary (by type with counts), cluster card grid (clickable). None of these exist. The hooks `useAIScores`, `useProblems`, `useRecommendations` are never called on this page.
**Fix:** Add 4 sections: (1) AI Readiness card with spider chart using `useAIScores`, (2) Issue Summary with horizontal bars using `useProblems`, (3) Recommendation Summary with type breakdown using `useRecommendations`, (4) Cluster grid using `useClusters`.
**Data source:** `useAIScores`, `useProblems`, `useRecommendations`, `useClusters` — all hooks exist
**Complexity:** Large (4 new sections with visualizations)

#### GAP-03: Today page missing 4-stat-card row and cluster health mini-table
**File:** `frontend/src/app/(dashboard)/today/page.tsx`
**Bug:** Spec requires 4 equal-width stat cards (Health Score, AI Ready %, Issues count, Recs pending). Current page has a health score card + trend card + sidebar-style quick stats. No dedicated "AI Ready" card, no cluster health mini-table. Six dashboard components in `components/dashboard/` (ClusterList, TrendChart, TopActionsCard, etc.) were built but never imported.
**Fix:** Replace the current layout with the spec's 4-card row using existing data hooks. Import and use the orphaned `ClusterList.tsx` component for the cluster health mini-table.
**Data source:** `useSiteHealth`, `useAIScores`, `useProblems`, `useRecommendations` — all fetched
**Complexity:** Medium

---

### HIGH — Spec says "launch priority"

#### GAP-04: Post detail missing factor weights, AI readiness spider, grade level
**File:** `frontend/src/app/(dashboard)/posts/[postId]/page.tsx`
**Bug:** Health factor breakdown bars show scores but not the weight each factor carries in the composite (e.g., "AI Readiness: 40/100 (28% weight)"). No per-post AI readiness spider chart with the 4 dimensions. Grade level field exists in the type but is never displayed. Body text content preview not shown.
**Fix:** (1) Add weight labels to factor bars: "AI Readiness: 40/100 — 28% of score". (2) Add mini spider chart component for per-post AI scores using `ai_signals` from the detail response. (3) Display `grade_level` next to readability: "Flesch 49 (Grade 11)". (4) Show first 500 chars of `body_text`.
**Data source:** Backend `post_health_scores` weights (need to expose from config), `ai_signals` (now in PostDetailResponse)
**Complexity:** Medium

#### GAP-05: Settings missing Export CSV, Generate PDF, Delete Site, Change Password, Delete Account
**File:** `frontend/src/app/(dashboard)/settings/page.tsx`
**Bug:** No export CSV button. No PDF generation button (backend endpoint `/audit/generate` exists). No delete site or delete account functionality. No change password flow. No account section showing user email.
**Fix:** Add a "Data" tab with: (1) Export CSV button → backend ZIP endpoint, (2) Generate PDF button → `POST /audit/generate`, (3) Delete Site Data button with confirmation. Add an "Account" section with email display, change password, delete account.
**Data source:** New backend endpoints for CSV export and delete site. Existing `/audit/generate` for PDF. Supabase Auth for password.
**Complexity:** Medium

#### GAP-06: No `/recommendations` URL route
**File:** Sidebar links to `/actions`, not `/recommendations`
**Bug:** The spec sidebar says "Recommendations" at `/recommendations`. The actual page lives at `/actions`. Direct URL navigation to `/recommendations` returns 404.
**Fix:** Either rename the folder from `actions` to `recommendations`, or add a redirect/alias.
**Complexity:** Small

#### GAP-07: Six orphaned dashboard components never imported
**Files:**
- `components/dashboard/ClusterList.tsx` — cluster health mini-table (built, never used)
- `components/dashboard/EfficiencyRatio.tsx` — content efficiency display (built, never used)
- `components/dashboard/HealthScoreCard.tsx` — health card with gauge (built, never used)
- `components/dashboard/PostBreakdown.tsx` — post type pie chart (built, never used)
- `components/dashboard/TopActionsCard.tsx` — top 3 actions display (built, never used)
- `components/dashboard/TrendChart.tsx` — health trend over time (built, never used)

**Fix:** Import these into the Today page and Overview page where they belong. ClusterList → Today page. HealthScoreCard → Overview. TopActionsCard → Today. TrendChart → Overview.
**Complexity:** Small (components are built — just need to import and wire up)

---

### MEDIUM — Spec completeness

#### GAP-08: Overview missing health gauge, health bar, content profile card
**File:** `frontend/src/app/(dashboard)/overview/page.tsx`
**Bug:** No circular health gauge. No gradient scale bar (Poor→Excellent). Content profile doesn't show readability, freshness %, or most common content type.
**Fix:** Add health gauge component (circular SVG). Add gradient bar with marker. Extend content profile card with readability score and freshness percentage.
**Complexity:** Medium

#### GAP-09: Clusters page missing rec count, sort controls, progress bars
**File:** `frontend/src/app/(dashboard)/clusters/page.tsx`
**Bug:** No recommendation count per cluster card. Sort is hardcoded to most-posts-first with no UI controls. No progress bar showing health score as filled portion.
**Fix:** (1) Count recs per cluster from `useRecommendations`. (2) Add sort dropdown (health ascending, post count, alphabetical). (3) Add a thin progress bar under each health score.
**Complexity:** Small

#### GAP-10: Issues page missing post title inline, quick fix, cluster filter
**File:** `frontend/src/app/(dashboard)/issues/page.tsx`
**Bug:** Issue cards show "View Post" link but not the post title inline. No quick fix suggestions ("Add a link from [suggested post]"). No cluster filter.
**Fix:** (1) Join post title into `ContentProblem` type (backend already returns `post_id`, need to add `post_title`). (2) Add quick fix text from problem details if available. (3) Add cluster filter using post→cluster mapping.
**Complexity:** Small

#### GAP-11: Three API hooks return data that no page consumes
**File:** `frontend/src/lib/hooks/useApi.ts`
- `useHealthHistory` (line 181) — fetches `/intelligence/health/history` but no page shows the health trend chart
- `useAlerts` (line 163) — fetches alert data but no alerts panel exists
- `useRedirectStatus` (line 82) — fetches redirect status but no page shows it

**Fix:** (1) Add health trend line chart to Overview page using `useHealthHistory`. (2) Add alerts integration to Today page "Recent Changes" card using `useAlerts`. (3) Add redirect status to Consolidation page using `useRedirectStatus`.
**Complexity:** Medium

#### GAP-12: Cannibalization page missing summary stats row
**File:** `frontend/src/app/(dashboard)/cannibalization/page.tsx`
**Bug:** No "Posts involved: N of total (pct%)", no "Average overlap", no "Pairs needing action" count. Only total pairs shown.
**Fix:** Compute from existing pairs data: `uniquePosts.size`, `avg(overlap_scores)`, `pairs.filter(p => p.severity === 'high' || p.severity === 'critical').length`.
**Complexity:** Small

#### GAP-13: Recommendations page missing confidence badge, search, pagination, post score
**File:** `frontend/src/app/(dashboard)/actions/page.tsx`
**Bug:** Confidence field exists in data but isn't displayed on cards. No text search for post title. No pagination (all recs load at once). No post health score shown on rec cards.
**Fix:** (1) Add confidence badge (High/Medium/Low) next to priority badge. (2) Add text search input filtering by post title. (3) Add client-side pagination (20/page). (4) Show post score on card footer.
**Complexity:** Small

---

### LOW — Post-launch polish

#### GAP-14: Billing page missing sites usage and invoice PDF download
**Complexity:** Small

#### GAP-15: Inbound links card on post detail shows placeholder text only
**File:** `posts/[postId]/page.tsx` line 481-489
**Complexity:** Small (data available, just needs rendering)

#### GAP-16: Before/after diff on re-analysis (retention hook)
**Complexity:** Large (needs per-post history comparison)

#### GAP-17: "AnalyticsOverview" type defined but never used
**File:** `frontend/src/lib/types.ts` line 109
**Complexity:** Small (wire up to overview page)

---

### IMPLEMENTATION ORDER

**Week 1 (Critical + High):**
1. GAP-01: Fix postMetaMap in Posts list (new bulk endpoint + client wiring) — **Day 1**
2. GAP-07: Import 6 orphaned components into Today + Overview — **Day 1**
3. GAP-03: Today page 4-stat-card row + cluster health mini-table — **Day 2**
4. GAP-06: Add `/recommendations` route alias — **Day 2** (30 min)
5. GAP-04: Post detail factor weights + grade level + body preview — **Day 2-3**
6. GAP-05: Settings export CSV + generate PDF + account section — **Day 3**

**Week 2 (Medium):**
7. GAP-02: Overview page 4 new sections (AI readiness, issues, recs, clusters) — **Day 4-5**
8. GAP-09: Clusters page sort controls + rec count + progress bars — **Day 5**
9. GAP-10: Issues page post title inline + cluster filter — **Day 5**
10. GAP-11: Wire up useHealthHistory for trend chart — **Day 6**
11. GAP-12 + GAP-13: Cannibalization summary stats + Recommendations search/pagination — **Day 6**

**Week 3 (Low):**
12. GAP-08: Health gauge + gradient bar — **Day 7**
13. GAP-14-17: Polish items — **Day 7-8**

---

## Local Development — Errors Found & Fixes Applied (March 30, 2026)

Full audit of every issue blocking `localhost` end-to-end operation. Each error, its root cause, file location, and the fix applied (or action required from the developer).

---

### ERR-01: CSP blocks frontend → backend API calls (FIXED)

**Symptom:** `Fetch API cannot load http://localhost:8000/v1/sites. Refused to connect because it violates the document's Content Security Policy.`

**Root cause:** `connect-src` in `frontend/next.config.mjs` only allowed `https://*.supabase.co` and `https://api.enough.app`. Missing `http://localhost:8000` for local dev.

**File:** `frontend/next.config.mjs` line 36

**Fix:** Added `http://localhost:8000` to `connect-src` conditionally when `NODE_ENV !== 'production'`:
```javascript
`connect-src 'self' https://*.supabase.co https://api.enough.app wss://*.supabase.co${isDev ? ' http://localhost:8000' : ''}`
```

---

### ERR-02: Supabase client crashes on empty URL (FIXED)

**Symptom:** `Error: supabaseUrl is required` — server-side crash on every page load.

**Root cause:** `@supabase/supabase-js` `createClient()` throws if URL is empty string. `.env.local` has `NEXT_PUBLIC_SUPABASE_URL=` (empty).

**File:** `frontend/src/lib/supabase.ts` lines 3-4

**Fix:** Fallback to `https://placeholder.supabase.co` (valid URL format, won't resolve but won't crash):
```typescript
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder';
```

---

### ERR-03: ERR_UNSAFE_PORT from Supabase placeholder (FIXED)

**Symptom:** `This site can't be reached — ERR_UNSAFE_PORT` when redirecting to `http://localhost:0/auth/v1/authorize`.

**Root cause:** Initial fix used `http://localhost:0` as placeholder — port 0 is blocked by browsers as unsafe.

**File:** `frontend/src/lib/supabase.ts` line 3

**Fix:** Changed placeholder to `https://placeholder.supabase.co` (port-safe, matches CSP wildcard).

---

### ERR-04: 403 "plan does not include access to sites" (FIXED)

**Symptom:** `API error 403: {"detail":"Your plan does not include access to sites, or you have reached your usage limit."}` on every dashboard page.

**Root cause:** Demo mode sends token `11111111-1111-1111-1111-111111111111` as Bearer auth. Backend dev mode accepts raw UUIDs. But:
1. No row in `auth.users` for this UUID
2. No row in `profiles` → `StripeService.check_usage_limits()` defaults to `free` tier
3. Free tier: `{"sites": 0, "posts": 0}` → blocks everything

**Files:**
- `backend/app/dependencies.py` lines 98-117 — `SubscriptionGuard` checks tier
- `backend/app/services/stripe_service.py` lines 20-24 — `TIER_LIMITS` definition
- `backend/app/services/stripe_service.py` lines 655-708 — `check_usage_limits()` queries profiles

**Fix:** Seeded demo user in database:
```sql
INSERT INTO auth.users (id, email) VALUES ('11111111-1111-1111-1111-111111111111', 'pipeline-test@tended.app');
INSERT INTO profiles (id, email, full_name, subscription_tier, subscription_status)
VALUES ('11111111-1111-1111-1111-111111111111', 'pipeline-test@tended.app', 'Demo User', 'growth', 'growth');
UPDATE sites SET user_id = '11111111-1111-1111-1111-111111111111' WHERE user_id IS NULL;
```

---

### ERR-05: Middleware redirects demo users to /login (FIXED)

**Symptom:** Navigating to `/today`, `/overview`, etc. redirects to `/login` even in demo mode.

**Root cause:** `middleware.ts` checks for Supabase auth cookies at the edge level. Demo mode has no cookies (fake session is client-side only in AuthProvider). Middleware runs before client JS.

**File:** `frontend/src/middleware.ts` lines 35-61

**Fix:** Added demo mode bypass at the top of the middleware function:
```typescript
if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
  return NextResponse.next();
}
```

---

### ERR-06: Dashboard paywall redirects to /billing (FIXED by ERR-04)

**Symptom:** Dashboard layout checks `useSubscription()` → tier is `free` → hard redirect to `/billing`.

**Root cause:** `frontend/src/app/(dashboard)/layout.tsx` lines 37-46 enforce paid tier. Without a profiles row, `/v1/billing/subscription` returns `{"tier":"free"}`.

**File:** `frontend/src/app/(dashboard)/layout.tsx` lines 37-46

**Fix:** Resolved by ERR-04 — demo user now has `growth` tier, so `useSubscription()` returns `{"tier":"growth"}`.

---

### ERR-07: Migration 040 fails on existing data (FIXED)

**Symptom:** `asyncpg.exceptions.CheckViolationError: new row for relation "content_problems" violates check constraint` when running `python migrate.py`.

**Root cause:** Migration renamed `geo_no_freshness_date → geo_no_updated_date` but ran the UPDATE before dropping the old CHECK constraint. Also, the new constraint was missing 4 problem types that exist in the DB: `readability_too_complex`, `seo_no_images`, `seo_no_internal_links`, `thin_below_cluster_avg`.

**File:** `backend/migrations/040_rename_freshness_problem.sql`

**Fix:** Reordered to DROP CONSTRAINT first, then UPDATE. Added all missing types to the new constraint.

---

### ERR-08: Google OAuth requires real Supabase project (NOT FIXABLE LOCALLY)

**Symptom:** Clicking "Sign in with Google" navigates to `placeholder.supabase.co` → DNS error.

**Root cause:** OAuth flow is handled by Supabase Auth, which redirects to the Supabase project URL. Without a real project, this is impossible.

**Developer action required:** To use Google OAuth:
1. Create a Supabase project at https://supabase.com
2. Enable Google OAuth in Authentication → Providers
3. Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `frontend/.env.local`
4. Set `SUPABASE_JWT_SECRET` in `backend/.env`

**Workaround:** Use demo mode (`NEXT_PUBLIC_DEMO_MODE=true`) which bypasses all auth.

---

### ERR-09: Magic link auth fails with placeholder Supabase (NOT FIXABLE LOCALLY)

**Symptom:** `TypeError: Failed to fetch` when submitting email for magic link — calls `placeholder.supabase.co/auth/v1/otp`.

**Root cause:** Same as ERR-08 — requires real Supabase project.

**File:** `frontend/src/providers/AuthProvider.tsx` line 100

**Workaround:** Demo mode bypasses this entirely.

---

### ERR-10: /docs endpoint disabled (backend shows as production) (KNOWN)

**Symptom:** `http://localhost:8000/docs` returns 404 even with `ENVIRONMENT=development` in `.env`.

**Root cause:** `backend/app/main.py` line 79 reads `os.environ.get("ENVIRONMENT", "production")` at module import time. `pydantic-settings` loads `.env` into the Settings object, but `os.environ` doesn't read `.env` files. Since `ENVIRONMENT` isn't exported to the OS environment, it defaults to `"production"`.

**File:** `backend/app/main.py` line 79

**Workaround:** Export the variable before starting:
```bash
export ENVIRONMENT=development && cd backend && uvicorn app.main:app --reload --port 8000
```

---

### ERR-11: Frontend .env.example has wrong API URL (DOCUMENTATION BUG)

**Symptom:** If developer copies `frontend/.env.example` → double `/v1` in API calls → all requests 404.

**Root cause:** `frontend/.env.example` line 6 has `http://localhost:8000/v1`, but `frontend/src/lib/api.ts` appends `/v1` automatically.

**Files:**
- `frontend/.env.example` — incorrect
- `frontend/.env.local.example` — correct (`http://localhost:8000`)
- `frontend/src/lib/api.ts` lines 1-10 — appends `/v1`

**Status:** Documented in CLAUDE.md as a known gotcha. `.env.local` already has the correct value.

---

### ERR-12: Pipeline features require real API keys (EXPECTED)

**Symptom:** Intelligence pipeline steps fail silently when API keys are missing/dummy.

**Required keys and what breaks without them:**

| Key | What breaks |
|-----|-------------|
| `OPENAI_API_KEY` | Embeddings (Step 2), clustering needs embeddings, health scoring |
| `ANTHROPIC_API_KEY` | Cluster labels (Step 6b), AI citability (Step 6c), Oracle, consolidation drafts |
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | GA4/GSC data sync, Google OAuth |
| `STRIPE_SECRET_KEY` | Checkout, portal, subscription management (billing page) |
| `RESEND_API_KEY` | Weekly email reports, pipeline completion notifications |

**Developer action:** These are expected — pipeline features require real API keys. The dashboard UI will render but show empty data for AI-powered features.

---

### ERR-13: SWR hooks silently disabled without auth token (BY DESIGN)

**Symptom:** Dashboard pages show infinite spinner, no error message.

**Root cause:** `frontend/src/lib/hooks/useSWRFetch.ts` lines 14-15 — SWR key is set to `null` when `session?.access_token` is falsy. SWR does not fetch when key is null.

**File:** `frontend/src/lib/hooks/useSWRFetch.ts`

**Status:** This is by-design — prevents unauthenticated API calls. Fixed by ERR-04 (demo mode now has a valid token that the backend accepts).

---

### Summary: What you need to provide for full local dev

| Requirement | Needed for | Can skip? |
|------------|------------|-----------|
| PostgreSQL (pgvector) on localhost:5433 | Database | No |
| `ENVIRONMENT=development` in backend/.env | Skip production validation, enable dev auth | No |
| `NEXT_PUBLIC_DEMO_MODE=true` in frontend/.env.local | Bypass Supabase auth | Yes, if you have Supabase |
| Demo user seeded in DB (growth tier) | Bypass subscription paywall | Yes, if you have Stripe |
| `NEXT_PUBLIC_SUPABASE_URL` + `ANON_KEY` | Real auth (login/signup/OAuth) | Yes, if using demo mode |
| `SUPABASE_JWT_SECRET` in backend/.env | JWT validation | Yes, dev mode accepts raw UUIDs |
| `OPENAI_API_KEY` | Embeddings, intelligence pipeline | Yes, dashboard still loads |
| `ANTHROPIC_API_KEY` | AI features (Oracle, labels, drafts) | Yes, dashboard still loads |
| `STRIPE_SECRET_KEY` | Billing checkout/portal | Yes, demo user has growth tier |
| `GOOGLE_CLIENT_ID` + `SECRET` | GA4/GSC integration | Yes, settings page just shows "not connected" |
| `RESEND_API_KEY` | Email delivery | Yes, non-blocking |

---

### Quick-start (minimal working local dev)

```bash
# 1. Start PostgreSQL (if not running)
docker run -d --name tended-postgres -p 5433:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=enough \
  pgvector/pgvector:pg16

# 2. Run migrations
cd backend && python migrate.py

# 3. Seed demo user (run once)
docker exec tended-postgres psql -U postgres -d enough -c "
INSERT INTO auth.users (id, email) VALUES ('11111111-1111-1111-1111-111111111111', 'pipeline-test@tended.app') ON CONFLICT DO NOTHING;
INSERT INTO profiles (id, email, full_name, subscription_tier, subscription_status) VALUES ('11111111-1111-1111-1111-111111111111', 'pipeline-test@tended.app', 'Demo User', 'growth', 'growth') ON CONFLICT (id) DO UPDATE SET subscription_status = 'growth', subscription_tier = 'growth';
"

# 4. Ensure backend/.env has:
#    DATABASE_URL=postgresql://postgres:postgres@localhost:5433/enough
#    ENVIRONMENT=development

# 5. Ensure frontend/.env.local has:
#    NEXT_PUBLIC_API_URL=http://localhost:8000
#    NEXT_PUBLIC_DEMO_MODE=true

# 6. Start backend
cd backend && uvicorn app.main:app --reload --port 8000

# 7. Start frontend (separate terminal)
cd frontend && npm run dev

# 8. Open http://localhost:3000 — auto-logged in as Demo User with growth tier
```