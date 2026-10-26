# AryaVeda Mehndi

Ayurvedic/organic mehndi artist marketplace — a single PWA (installable as
an app, crawlable as a website) with a FastAPI + PostgreSQL backend. Full
design rationale: see the Arya Mehndi Blueprint artifact from planning.

Brand name: **AryaVeda Mehndi**. The project folder, database name
(`aryamehndi`), and internal package identifiers were kept as-is — they're
just internal technical labels, not user-facing, so renaming them would be
pure churn with no benefit.

## What's built

- **Backend** (`backend/`) — FastAPI + PostgreSQL. Phone-OTP auth, nearby
  artist discovery, packages, the full booking state machine, price
  negotiation, gender-matched safety preference, geo check-in/out,
  photo-gated payment with design-similarity verification, Razorpay
  platform-fee collection, reviews/reports/strikes, and an admin-editable
  CMS. Verified: imports cleanly, boots, serves `/health` and `/docs`.
- **Frontend** (`frontend/`) — Next.js PWA (installable, manifest + service
  worker), Tailwind, all content/packages/CMS copy fetched from the
  backend. Pages: home, phone-OTP login, nearby-artist discovery, booking +
  negotiation + status tracking + design confirmation + payment + reviews,
  an artist dashboard (profile/KYC/availability/bookings), and an admin
  panel (packages, KYC approvals, reports, brand content). Verified: `npm
  run build` completes cleanly.

## First-time setup (do this once)

Commands are for macOS/Linux; on Windows use `venv\Scripts\...` instead of
`venv/bin/...` and `copy` instead of `cp`.

**1. Database.** With Postgres 17 running locally, create the app's role +
database (you'll be prompted for your `postgres` superuser password):

```
psql -U postgres -h localhost -f backend/setup_db.sql
```

**2. Backend env, migrations and seed data:**

```
cd backend
python3 -m venv venv && venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
venv/bin/alembic upgrade head
venv/bin/python seed.py            # packages, admin user, CMS copy
venv/bin/python seed_designs.py    # design catalog + gallery images
venv/bin/python seed_shop.py       # shop catalogue (loads as hidden drafts)
venv/bin/python set_admin_password.py admin   # username/password admin login
```

**3. Frontend env** (defaults are fine for local dev):

```
cd frontend
npm install
cp .env.local.example .env.local
```

## Running it

Two terminals:

```
cd backend
venv/bin/uvicorn app.main:app --reload --port 8000
```

```
cd frontend
npm run dev
```

Open http://localhost:3000. API docs at http://localhost:8000/docs.

Log in with any phone number — OTP dev mode prints the code to the
backend terminal (and returns it in the login screen) since no SMS
provider is configured yet. The seed script also creates an admin user on
phone `9999999999` — log in with that number to reach `/admin`.

## To try the full booking flow locally

1. Log in as an **artist** (any other phone number, choose "I'm a mehndi
   artist"), fill in the profile (needs location permission), upload a
   dummy KYC doc + selfie.
2. Log in as **admin** (`9999999999`) → Admin → KYC Approvals → approve
   that artist.
3. Log in as a **consumer**, go to Discover, allow location, book the
   approved artist, optionally propose a price.
4. Switch back to the artist tab, accept the offer if one was made, mark
   en route → arrived → start → upload a design photo.
5. Back on the consumer side: confirm the design, pay the platform fee
   (Razorpay isn't configured, so this auto-completes in dev mode), leave
   a review.

## Testing the installable app

The app installs from the browser as a Progressive Web App - there's no
app-store download. `/download` shows an **Install app** button where the
browser supports it (Chrome, Edge, Samsung Internet) and step-by-step
instructions elsewhere (Safari on iPhone/iPad/Mac). Two rules decide
whether a browser will offer to install at all:

1. **A service worker must be running.** It's disabled under `npm run dev`,
   so test install against a production build:

   ```
   cd frontend
   npm run build && npm start
   ```

2. **The page must be https** (or `localhost` on the same computer). A
   phone opening `http://192.168.x.x:3000` won't offer install. To test
   on a phone, expose your local build over https with a tunnel, e.g.
   `npx localtunnel --port 3000` or `cloudflared tunnel --url http://localhost:3000`,
   and open the https URL it prints on the phone.

| Device | Where to test | What to expect |
|---|---|---|
| Mac - Chrome/Edge | http://localhost:3000/download | **Install app** button; app opens in its own window, appears in Launchpad |
| Mac - Safari 17+ (macOS 14+) | same | File → Add to Dock |
| Android - Chrome | tunnel https URL | **Install app** button, or ⋮ → Add to Home screen → Install |
| iPhone/iPad - Safari | tunnel https URL | Share → Add to Home Screen |

To check installability in Chrome: DevTools → Application → Manifest
(shows install errors) and → Service workers. To start over, uninstall the
app (Chrome: open the app → ⋮ → Uninstall) and clear site data.

## Going live checklist

The backend refuses to start with `APP_ENV=production` until the unsafe
dev settings are gone: a real `JWT_SECRET` (32+ chars), `OTP_DEV_MODE=false`,
`CORS_ORIGINS` set to the real site, Razorpay live keys + webhook secret,
and MSG91 key + OTP template (registered on TRAI DLT).

**Run the worker.** Refunds, the Razorpay event inbox, emails, releasing
unpaid orders and the daily reconciliation all run in a background worker.
Run it as its own always-on process next to the API (one is enough; more
are safe):

```
cd backend
venv/bin/python -m app.worker
```

If it isn't running, Admin → Payments shows a "jobs have been waiting"
alert.

**Razorpay webhook** (Dashboard → Settings → Webhooks): URL
`<PUBLIC_API_URL>/payments/razorpay/webhook`, events `payment.captured`,
`order.paid`, `refund.processed`, `refund.failed`, and the secret you put
in `RAZORPAY_WEBHOOK_SECRET`.

Also set before launch:

- **Backend `.env`:** `S3_*` (so uploads survive server replacement),
  `PUBLIC_SITE_URL`, `PUBLIC_API_URL`, seller details for invoices
  (`BUSINESS_LEGAL_NAME`, `BUSINESS_ADDRESS`, `BUSINESS_STATE`,
  `BUSINESS_GSTIN`, `SUPPORT_EMAIL`, `SUPPORT_PHONE`), `SMTP_*` for order
  emails with the receipt, invoice and credit-note PDFs, and optionally
  `EXOTEL_*` for masked calling (without it the call button is hidden in
  production).
- **Frontend env:** `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_SITE_URL`, the
  seller and grievance-officer details (`NEXT_PUBLIC_BUSINESS_*`,
  `NEXT_PUBLIC_SUPPORT_*`, `NEXT_PUBLIC_GRIEVANCE_OFFICER_*` — the policy
  pages highlight anything missing), and `NEXT_PUBLIC_GA_MEASUREMENT_ID` /
  `NEXT_PUBLIC_META_PIXEL_ID` for analytics and ad tracking.
- **Admin panel:** stock for each pack size, licence numbers for licensed
  products and HSN code + GST rate for invoices (Shop Products); delivery
  charge, payment window and Cash on Delivery limits (Settings); any launch
  coupons (Coupons). Admin → Payments is the place to watch refunds,
  reconciliation and failed jobs.
- **Ads:** point Meta Commerce Manager / Google Merchant Center at
  `<PUBLIC_API_URL>/shop/feed.csv` as a scheduled product feed.

## What's stubbed vs. production-ready

See `backend/README.md` for the full table (OTP/SMS, Razorpay, PostGIS,
ML design-matching, file storage, background jobs) — every stub is a
config change away from the real thing, not a rewrite.

## Known limitation from setup

PostGIS wasn't installed alongside this Postgres instance, so nearby-artist
search uses plain-SQL Haversine distance instead — accurate enough at
city scale. Install the PostGIS extension later if the artist count grows
large enough that this becomes a real query-performance bottleneck.
