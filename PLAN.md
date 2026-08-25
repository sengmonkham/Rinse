# RINSE — Web App & Paid-Status Plan

## Locked decisions

| Area | Decision |
|---|---|
| Repo | **New separate repo `rinse-web`** — this repo stays pure Chrome extension + AI server |
| Web app | Next.js (App Router) + TypeScript, deployed to Vercel |
| Database | **Neon** (serverless Postgres) — 0.5 GB storage / 100 CU-hr free tier, scale-to-zero |
| Auth | **Better Auth** — users, sessions, accounts natively in Neon Postgres (email + Google OAuth) |
| Payments | **Dodo Payments** — Merchant of Record (handles EU VAT / global sales tax), subscriptions, HMAC webhooks, public license-key validate API |
| Paid-status flow | Dodo webhook → update user's `subscriptions` row in Neon → extension calls `GET /api/v1/me` |
| Paywall | None yet — build the status plumbing + UI only |

## Architecture

```
┌─ Chrome Extension (this repo) ─────┐     ┌─ NEW REPO: rinse-web (Next.js) ────────────────┐
│  popup/dashboard (React)           │     │  /  /pricing  /sign-in  /account (landing+login)│
│  Settings: "Account" card          │────▶│  /api/v1/me            /api/webhooks/dodo       │
│  background.js: paid-status check  │     │  Better Auth (sessions in Neon)                 │
└────────────────┬───────────────────┘     └───────────────┬──────────────────────────────────┘
                 │  GET /api/v1/me (Bearer token)          │ checkout redirect
                 ▼                                        ▼
        ┌─────────────────────────┐               ┌─ Dodo Payments (MoR) ─┐
        │  Neon Postgres          │◀── webhook ───│  checkout, subs, tax   │
        │  users + subscriptions  │   (HMAC)      │  license keys          │
        └─────────────────────────┘               └────────────────────────┘
```

## Paid-status loop (webhook-driven, per decision)

1. User clicks "Upgrade to Pro" on `/pricing` → `POST /api/checkout` → redirect to Dodo hosted checkout.
2. Dodo fires `subscription.active` (also `.updated`, `.plan_changed`, `.cancelled`, `.expired`, `.on_hold`).
3. `/api/webhooks/dodo` verifies the HMAC signature (`DODO_WEBHOOK_KEY`), then upserts the user's `subscriptions` row in Neon.
4. The extension authenticates (Better Auth token via bearer header) and calls `GET /api/v1/me` → reads Neon → `{ is_paying, plan, expires_at }`.
5. Result cached in `chrome.storage.local`, re-checked on extension startup + via `chrome.alarms` (e.g. every 6h).

The extension never talks to Dodo — the Neon row is the single source of truth.

## Neon schema (initial migration)

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  name text,
  created_at timestamptz not null default now()
);

create table subscriptions (
  user_id uuid primary key references users(id) on delete cascade,
  plan text not null default 'free',          -- 'free' | 'pro'
  status text not null default 'inactive',    -- 'inactive' | 'active' | 'cancelled' | 'past_due'
  provider text default 'dodo',
  provider_customer_id text,
  provider_subscription_id text,
  license_key text,
  current_period_end timestamptz,
  updated_at timestamptz not null default now()
);
```

Better Auth adds its own tables (`user`, `session`, `account`, `verification`) via its schema adapter.

## New repo (`rinse-web`) structure

```
rinse-web/
├─ app/
│  ├─ page.tsx                    # landing: hero, features, how-it-works
│  ├─ pricing/page.tsx            # Free vs Pro, upgrade → /api/checkout
│  ├─ sign-in/page.tsx            # Better Auth UI (email + Google OAuth)
│  ├─ account/page.tsx            # protected: plan badge, Manage subscription
│  ├─ privacy/page.tsx, terms/page.tsx
│  └─ api/
│     ├─ webhooks/dodo/route.ts   # HMAC verify → Neon upsert
│     ├─ v1/me/route.ts           # bearer auth → { is_paying, plan, expires_at }
│     └─ checkout/route.ts        # create Dodo checkout, link user
├─ lib/db.ts                      # @neondatabase/serverless connection
├─ lib/auth.ts                    # Better Auth server config
├─ drizzle/ or migrations/        # schema migrations
└─ .env.local                     # DATABASE_URL, DODO_API_KEY, DODO_WEBHOOK_KEY, BETTER_AUTH_*
```

## This repo (extension) changes

- **`src/components/Settings.tsx`** — add "Account" card: sign-in state, Free/Pro badge, plan expiry, "Manage subscription" deep-link to `rinse-web` account page.
- **`public/background.js`** — on install + `chrome.alarms` periodic check: call `/api/v1/me` with cached token, store `{ isPaying, plan, expiresAt }` in `chrome.storage.local`; expose via runtime message for the popup.
- **No feature gating yet** — plumbing and status display only (paywall decided later).

## Execution order

1. Scaffold `rinse-web`: Next.js + TS, Neon project + migration, Better Auth (email + Google OAuth).
2. Landing page (`/`, `/pricing`) with the extension's dark glassy aesthetic.
3. Sign-in + protected `/account`.
4. Dodo checkout + `/api/webhooks/dodo` + `/api/v1/me`.
5. Extension integration (Settings Account card + background paid-status check).
6. Deploy: web app → Vercel, extension → Chrome Web Store, `server.py` → HF Spaces.

## Credentials needed (when we build)

- Neon: `DATABASE_URL` (https://neon.tech → console → connection string)
- Dodo: `DODO_API_KEY`, `DODO_WEBHOOK_KEY` (https://dodopayments.com)
- Better Auth: `BETTER_AUTH_SECRET`, Google OAuth `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
