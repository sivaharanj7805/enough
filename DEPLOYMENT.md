# Tended — Production Deployment Guide

Architecture: `usetended.io` (Vercel) + `api.usetended.io` (Railway) + Supabase (Auth + Postgres)

---

## 1. Supabase

You already have a project: `xczsmgrtdkqswppbbkzd.supabase.co`

### 1a. Grab Your Credentials

Go to **Project Settings → API** and copy:

| Value | Where to find it | Env var |
|-------|-----------------|---------|
| Project URL | Top of API page | `SUPABASE_URL` |
| anon public key | Under "Project API keys" | `SUPABASE_KEY` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| service_role key | Under "Project API keys" (click reveal) | `SUPABASE_SERVICE_KEY` |
| JWT Secret | Settings → API → JWT Settings | `SUPABASE_JWT_SECRET` |

### 1b. Get Your Database Connection String

Go to **Project Settings → Database → Connection string → URI**

- Select **"Session"** mode (port 5432) — not Transaction mode
- Copy the full URI and replace `[YOUR-PASSWORD]` with your database password
- This becomes your `DATABASE_URL`

It looks like: `postgresql://postgres.xczsmgrtdkqswppbbkzd:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres`

### 1c. Configure Authentication

Go to **Authentication → URL Configuration**:

| Field | Value |
|-------|-------|
| Site URL | `https://usetended.io` |
| Redirect URLs | Add: `https://usetended.io/**` |

Go to **Authentication → Providers**:

- **Email**: Should already be enabled (email/password signup)
- **Google** (optional — for "Sign in with Google" button):
  - You'll set this up after creating the Google Cloud project in Section 4
  - Come back here and paste your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
  - Set Authorized redirect URL to what Supabase shows you

### 1d. Enable pgvector Extension

Go to **Database → Extensions** and enable:

- `vector` (pgvector — needed for embeddings)

If it's already enabled, skip this.

---

## 2. Stripe

### 2a. Create Products and Prices

Go to **Stripe Dashboard → Products** and create two products:

**Product 1: Tended Growth**

| Field | Value |
|-------|-------|
| Name | Tended Growth |
| Description | 1 site, 500 posts, full landscape & dashboard |
| Price (Monthly) | $149.00 / month, Recurring |

After creating, click into the price and copy the **Price ID** (starts with `price_`).
This is your `STRIPE_PRICE_GROWTH`.

**Product 2: Tended Scale**

| Field | Value |
|-------|-------|
| Name | Tended Scale |
| Description | Up to 3 sites, 2000 posts, unlimited consolidations |
| Price (Monthly) | $349.00 / month, Recurring |

Copy the Price ID → this is your `STRIPE_PRICE_SCALE`.

> Note: The code currently maps one price ID per tier. If you want annual pricing
> ($1,490/year Growth, $3,490/year Scale), you'll need to add `STRIPE_PRICE_GROWTH_ANNUAL`
> and `STRIPE_PRICE_SCALE_ANNUAL` env vars and update `stripe_service.py` later.
> For launch, monthly-only is fine.

### 2b. Create Webhook Endpoint

Go to **Developers → Webhooks → Add endpoint**:

| Field | Value |
|-------|-------|
| Endpoint URL | `https://api.usetended.io/v1/billing/webhook` |
| Description | Tended production webhook |
| Listen to | Select these specific events: |

Events to subscribe to:
- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `customer.subscription.paused`
- `invoice.payment_failed`

After creating, click **Reveal** on the signing secret.
This is your `STRIPE_WEBHOOK_SECRET` (starts with `whsec_`).

### 2c. Get Your API Keys

Go to **Developers → API keys**:

| Value | Env var |
|-------|---------|
| Secret key (starts with `sk_live_`) | `STRIPE_SECRET_KEY` |
| Publishable key (starts with `pk_live_`) | `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` |

> Use **test keys** (`sk_test_` / `pk_test_`) for initial testing.
> Switch to live keys when ready for real payments.
> You'll also need a separate test webhook endpoint for test mode.

---

## 3. Resend (Transactional Email)

### 3a. Create Account and API Key

1. Go to [resend.com](https://resend.com) and sign up
2. Go to **API Keys → Create API Key**
   - Name: `tended-production`
   - Permission: Full access
   - Copy the key → this is your `RESEND_API_KEY` (starts with `re_`)

### 3b. Verify Your Domain

Go to **Domains → Add Domain**:

| Field | Value |
|-------|-------|
| Domain | `usetended.io` |

Resend will give you DNS records to add:

| Type | Name | Value | Purpose |
|------|------|-------|---------|
| TXT | (varies) | (varies) | SPF record |
| CNAME | (varies) | (varies) | DKIM record |
| TXT | `_dmarc` | (varies) | DMARC record |

Add ALL of these in your DNS provider. Click **Verify** after adding them.

Once verified, emails will send from `reports@usetended.io` (configured in `config.py` as `EMAIL_FROM`).

---

## 4. Google Cloud (for Customer Google OAuth)

This is NOT for "Sign in with Google" — this is for your customers connecting their Google Search Console and Google Analytics accounts.

### 4a. Create Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project: **Tended**

### 4b. Enable APIs

Go to **APIs & Services → Library** and enable:

- **Google Search Console API** (also called "Google Search Console URL Testing Tools API")
- **Google Analytics Data API** (the GA4 one, NOT the old Universal Analytics)
- **Google Analytics Admin API**

### 4c. Configure OAuth Consent Screen

Go to **APIs & Services → OAuth consent screen**:

| Field | Value |
|-------|-------|
| App type | External |
| App name | Tended |
| User support email | your email |
| App logo | Upload your logo (optional but recommended) |
| App home page | `https://usetended.io` |
| Privacy policy | `https://usetended.io/privacy` |
| Terms of service | `https://usetended.io/terms` |
| Authorized domains | `usetended.io` |
| Developer contact | your email |

**Scopes** — add these:
- `https://www.googleapis.com/auth/webmasters.readonly`
- `https://www.googleapis.com/auth/analytics.readonly`
- `openid`
- `email`

**Test users** — while in "Testing" status, only users you list here can connect.
Add your own email for testing. Once you're ready for real customers, submit for verification (see 4e).

### 4d. Create OAuth Client ID

Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**:

| Field | Value |
|-------|-------|
| Application type | Web application |
| Name | Tended Production |
| Authorized JavaScript origins | `https://usetended.io` |
| Authorized redirect URIs | `https://api.usetended.io/v1/auth/google/callback` |

After creating, copy:

| Value | Env var |
|-------|---------|
| Client ID | `GOOGLE_CLIENT_ID` |
| Client secret | `GOOGLE_CLIENT_SECRET` |

Also set: `GOOGLE_REDIRECT_URI=https://api.usetended.io/v1/auth/google/callback`

### 4e. Google Verification (Required Before Real Customers)

While your app is in "Testing" mode, only manually-added test users (max 100) can connect.
To allow any Google user to connect their GSC/GA4:

1. Go to **OAuth consent screen → Publish App**
2. Google will ask you to:
   - Verify domain ownership of `usetended.io`
   - Submit for review (since you use restricted scopes)
   - Provide a YouTube video showing the OAuth flow
3. Review takes **2-6 weeks**

You can launch with test mode first — just add your early customers as test users manually while waiting for verification.

---

## 5. DNS Records

In your domain registrar (wherever you bought `usetended.io`), add these records:

### Vercel (Frontend)

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `@` | `76.76.21.21` | 3600 |
| CNAME | `www` | `cname.vercel-dns.com` | 3600 |

> Vercel will show you the exact records when you add the custom domain in their dashboard.
> These are their standard values but check what they display.

### Railway (Backend API)

| Type | Name | Value | TTL |
|------|------|-------|-----|
| CNAME | `api` | `[your-app].up.railway.app` | 3600 |

> Railway will show you the exact CNAME target when you add `api.usetended.io` as a custom domain.

### Resend (Email)

Add the SPF, DKIM, and DMARC records from Section 3b.

---

## 6. Railway (Backend Deployment)

### 6a. Connect Repository

1. Go to your Railway project
2. **New Service → GitHub Repo** → select `enough-1`
3. Railway will detect the `railway.toml` and root `Dockerfile`

### 6b. Configure Service Settings

In the service settings:

| Setting | Value |
|---------|-------|
| Root Directory | `/` (default) |
| Custom Domain | `api.usetended.io` |

### 6c. Set Environment Variables

In the service **Variables** tab, add every variable below.
Generate secrets with: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

```
# ── App ──
ENVIRONMENT=production
SECRET_KEY=<generate-64-char-random-string>

# ── Database (from Supabase Section 1b) ──
DATABASE_URL=postgresql://postgres.xczsmgrtdkqswppbbkzd:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres

# ── Supabase Auth (from Section 1a) ──
SUPABASE_URL=https://xczsmgrtdkqswppbbkzd.supabase.co
SUPABASE_KEY=<anon-key-from-supabase>
SUPABASE_SERVICE_KEY=<service-role-key-from-supabase>
SUPABASE_JWT_SECRET=<jwt-secret-from-supabase>

# ── AI APIs ──
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# ── Stripe (from Section 2) ──
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_GROWTH=price_...
STRIPE_PRICE_SCALE=price_...

# ── Email (from Section 3) ──
RESEND_API_KEY=re_...

# ── Google OAuth (from Section 4d) ──
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=https://api.usetended.io/v1/auth/google/callback

# ── URLs ──
FRONTEND_URL=https://usetended.io
CORS_ORIGINS=https://usetended.io

# ── Security ──
CRON_SECRET=<generate-random-string>
ALLOWED_HOSTS=api.usetended.io

# ── Optional ──
SENTRY_DSN=<if-you-have-one>
SLACK_WEBHOOK_URL=<if-you-want-slack-notifications>
```

### 6d. Deploy

Push to `master` or trigger a deploy in Railway dashboard.

Railway will:
1. Build the Docker image
2. Run `python migrate.py` (applies all 42 migrations to Supabase Postgres)
3. Start `uvicorn` on Railway's assigned port

### 6e. Verify

Once deployed, check: `https://api.usetended.io/health`

Expected response:
```json
{
  "status": "ok",
  "service": "tended-backend",
  "version": "0.1.0",
  "database": "connected"
}
```

If you see `"database": "disconnected"`, double-check your `DATABASE_URL`.

---

## 7. Vercel (Frontend Deployment)

### 7a. Configure Project

In your Vercel project dashboard:

| Setting | Value |
|---------|-------|
| Framework Preset | Next.js |
| Root Directory | `frontend` |
| Build Command | `npm run build` (default) |
| Node.js Version | 20.x |

### 7b. Add Custom Domain

Go to **Settings → Domains** and add:
- `usetended.io`
- `www.usetended.io` (redirects to `usetended.io`)

Vercel will show you the DNS records needed (should match Section 5).

### 7c. Set Environment Variables

Go to **Settings → Environment Variables** and add:

```
NEXT_PUBLIC_API_URL=https://api.usetended.io
NEXT_PUBLIC_SUPABASE_URL=https://xczsmgrtdkqswppbbkzd.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key-from-supabase>
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_...
NEXT_PUBLIC_DEMO_MODE=false
```

> IMPORTANT: `NEXT_PUBLIC_*` vars are baked into the build.
> After adding/changing these, you must **redeploy** for changes to take effect.
> Go to Deployments → click "..." on latest → Redeploy.

### 7d. Verify

Go to `https://usetended.io` — landing page should load.

---

## 8. Post-Deploy Verification Checklist

Run through this after everything is deployed:

### Infrastructure
- [ ] `https://api.usetended.io/health` returns `{"database":"connected"}`
- [ ] `https://usetended.io` loads the landing page
- [ ] SSL certificates are active on both domains (green lock)

### Auth Flow
- [ ] Sign up with email/password — confirmation email received
- [ ] Confirm email — redirected to onboarding
- [ ] Accept terms of service
- [ ] Log out and log back in

### Billing Flow
- [ ] Free user gets redirected to /billing
- [ ] Click "Upgrade" on Growth plan
- [ ] Stripe checkout loads with correct price ($149/mo)
- [ ] Complete test payment (use Stripe test card `4242 4242 4242 4242`)
- [ ] Redirected back, subscription active
- [ ] Dashboard now accessible

### Site Creation + Pipeline
- [ ] Create a site on onboarding page (enter a blog URL)
- [ ] Crawl starts and progress updates appear
- [ ] Pipeline completes (all 10 steps)
- [ ] Dashboard shows data (clusters, health scores, etc.)

### Google Integration
- [ ] Go to Settings → Integrations → Connect Google
- [ ] Google consent screen appears with "Tended" branding
- [ ] After consent, redirected back to settings
- [ ] GSC sites listed (if connected to a GSC property)
- [ ] GA4 properties listed

### Email
- [ ] Password reset email sends and works
- [ ] Weekly digest sends (test via cron endpoint if available)

---

## 9. Switching from Test to Live

When you're ready for real customers:

1. **Stripe**: Replace `sk_test_` / `pk_test_` with `sk_live_` / `pk_live_` keys
2. **Stripe Webhook**: Create a new webhook endpoint for live mode (test and live are separate in Stripe)
3. **Google**: Submit your OAuth app for verification (Section 4e)
4. **Supabase**: Already production-ready
5. **Resend**: Already production-ready (sending limit increases as you send more)

---

## Quick Reference: All Environment Variables

### Railway (Backend) — 20 variables

| Variable | Example | Required |
|----------|---------|----------|
| `ENVIRONMENT` | `production` | Yes |
| `SECRET_KEY` | `<random-64-chars>` | Yes |
| `DATABASE_URL` | `postgresql://postgres.xxx:pass@...` | Yes |
| `SUPABASE_URL` | `https://xxx.supabase.co` | Yes |
| `SUPABASE_KEY` | `eyJ...` | Yes |
| `SUPABASE_SERVICE_KEY` | `eyJ...` | Yes |
| `SUPABASE_JWT_SECRET` | `<from-supabase>` | Yes |
| `OPENAI_API_KEY` | `sk-...` | Yes |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Yes |
| `STRIPE_SECRET_KEY` | `sk_live_...` | Yes |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | Yes |
| `STRIPE_PRICE_GROWTH` | `price_...` | Yes |
| `STRIPE_PRICE_SCALE` | `price_...` | Yes |
| `RESEND_API_KEY` | `re_...` | Yes |
| `GOOGLE_CLIENT_ID` | `...apps.googleusercontent.com` | Yes |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-...` | Yes |
| `GOOGLE_REDIRECT_URI` | `https://api.usetended.io/v1/auth/google/callback` | Yes |
| `FRONTEND_URL` | `https://usetended.io` | Yes |
| `CORS_ORIGINS` | `https://usetended.io` | Yes |
| `CRON_SECRET` | `<random-string>` | Yes |
| `ALLOWED_HOSTS` | `api.usetended.io` | No |
| `SENTRY_DSN` | `https://...@sentry.io/...` | No |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/...` | No |

### Vercel (Frontend) — 5 variables

| Variable | Example | Required |
|----------|---------|----------|
| `NEXT_PUBLIC_API_URL` | `https://api.usetended.io` | Yes |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | Yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...` | Yes |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | `pk_live_...` | Yes |
| `NEXT_PUBLIC_DEMO_MODE` | `false` | No |


THINGS THAT I HAVE IDENTIFIED:
- how do i get STRIPE_PRICE_GROWTH and STRIPE_PRICE_SCALE
- i get this: {"code":400,"error_code":"validation_failed","msg":"Unsupported provider: provider is not enabled"}, when i try logging 
  in with google, or signing up with google
- when someone signs up for free, they dont have the option to come up with a free pdf of their blog/website.they dont have the option to insert their website for a free pdf. 
-