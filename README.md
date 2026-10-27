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

## Deploying (Docker Compose)

Everything runs from `deploy/`: Postgres 17, a one-off migration, the API,
the background worker, the website and Caddy (HTTPS with automatic
certificates). Long-running services restart on failure and have health
checks; the API and worker start only after migrations succeed.

**Server, once.** Install Docker, then:

```
mkdir -p /opt/aryaveda/deploy && cd /opt/aryaveda/deploy
# copy deploy/.env.example here as .env and fill in domains, secrets, keys
# (BACKEND_IMAGE / WEB_IMAGE already point at this repo's GHCR images)
```

**Releases are shipped by CI** (`.github/workflows/`):

| Workflow | When | What |
|---|---|---|
| `Pull request` (`staging.yml`) | every PR | Checks (`ci.yml`). With repo variable `STAGING_ENABLED=true`, also builds images tagged `pr-<n>-<sha>` and deploys them to the staging server |
| `Deploy` (`deploy.yml`) | push to `main` | Checks, then builds the backend and website images once, pushes them to GHCR (`ghcr.io/aniketkumarsingh/aryavedamehndi-{backend,web}:<sha>` and `:latest`), then deploys over SSH |
| `CI` (`ci.yml`) | called by both | Backend tests, migration round trip + safety check, frontend lint/tests/build |

The deploy copies `deploy/` to the server and runs `deploy.sh <sha>`: pull
the images, run migrations, start the new release, then smoke-test it -
`/health/ready` must report the new release with a working database, and
the website must answer. If it doesn't, the previous release is started
again (`deploy.sh --rollback` does the same by hand). Migrations are never
rolled back, so they must stay compatible with the previous release: add
columns and tables first, drop them in a later release.
`scripts/check_migrations.py` fails a PR that drops, renames or retypes
anything without a reviewed `# migration-safe: <reason>` note.

GitHub setup, per environment (`production`, `staging`) in Settings →
Environments: secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
(a key for a user in the `docker` group), `DEPLOY_KNOWN_HOSTS`
(`ssh-keyscan <host>` output); variables `DEPLOY_PATH` (`/opt/aryaveda`),
`SITE_DOMAIN`, `API_DOMAIN` and the website's public values
(`NEXT_PUBLIC_GA_MEASUREMENT_ID`, `NEXT_PUBLIC_META_PIXEL_ID`,
`NEXT_PUBLIC_SENTRY_DSN`, `BUSINESS_*`, `SUPPORT_*`, `GRIEVANCE_OFFICER_*`)
which are baked into the website image. Without `DEPLOY_SSH_KEY` the
images are still pushed and nothing is deployed.

Building on the server instead (no CI): leave `BACKEND_IMAGE`/`WEB_IMAGE`
empty and run `IMAGE_TAG=$(git rev-parse --short HEAD) docker compose up -d --build`.

First run only: load the catalogue with
`docker compose run --rm api python seed.py` (and `seed_designs.py`,
`seed_shop.py`), then `docker compose run --rm api python set_admin_password.py admin`.

**Logs.** Each line is JSON with `request_id` (also the `X-Request-ID`
response header, set by Caddy), `user_id`, `order_id` and, in the worker,
`job`. Follow one order through the API and the worker:
`docker compose logs api worker | grep '"order_id": "<id>"'`. Requests
slower than `SLOW_REQUEST_MS` (1500) are logged as `slow request` warnings.

**Monitoring.** Point an uptime monitor (UptimeRobot, Better Stack) at
`https://<API_DOMAIN>/health/ready`, alerting your phone. It returns 503
when the database is unreachable, the worker has stopped, jobs are piling
up, or there's been no backup for 36 hours. Set `SENTRY_DSN` and
`NEXT_PUBLIC_SENTRY_DSN` to get API, worker and browser errors (tagged with
the release), including any background job that gives up.

**Rate limits.** Per IP and per phone/user, on OTP send and verify, admin
login, coupon checks and checkout (`app/services/rate_limit.py`); over the
limit returns 429 with Retry-After.

### Shipping

Admin → **Shipping** is the daily dispatch screen: tick the confirmed
orders, enter the courier, **Book** (each order is shipped, its GST invoice
issued and the customer told), then print **Labels** (4×6 in, with an AWB
barcode) and the pickup **Manifest** for the courier to sign. Add AWB
numbers and tracking updates there (out for delivery, failed attempt,
returning…) - each update notifies the customer and moves the order.
Checkout checks the PIN code (deliverable, Cash on Delivery, estimated
dates) against the blocked prefixes and delivery estimate in Settings.

Fill in each pack size's packed weight and box (Admin → Shop Products) so
parcels are weighed correctly; until then the default weight in Settings
is used.

This runs on the built-in **manual** provider (no courier account). A
courier aggregator plugs in later as one class in
`app/services/shipping/` (serviceability, booking with AWB + label,
tracking, signed webhooks at `/shipping/webhook/<provider>`) and
`SHIPPING_PROVIDER=<name>` - the dispatch screen, tracking history,
notifications and 2-hourly tracking poll then work against the courier.

### Backups and restore

The worker runs `ops.backup_database` nightly at 01:30 IST: `pg_dump`
(custom format), checked readable with `pg_restore --list`, uploaded to
`BACKUP_S3_BUCKET` (or `S3_BUCKET`) under `backups/`, kept 30 days. Without
S3 it writes to the `backups` volume instead - set S3 in production so a
lost server doesn't take the backups with it. Admin → Payments and
`/health/ready` warn if a night is missed.

Restore (into a scratch database first, to check it):

```
scripts/restore_backup.sh s3://<bucket>/backups/aryaveda-YYYYMMDD-HHMMSS.dump postgresql://user:pass@host:5432/aryamehndi_restore
```

Restore drill log:

| Date | Where | Result |
|---|---|---|
| 26 Oct 2026 | Local dev (Postgres 16): backup job → `restore_backup.sh` into a scratch database | All 37 tables, 801 rows matched the source; schema at 0027 |

Repeat the drill on production data after launch and add a row.

### Growth

Admin → **Growth** holds the weekly dashboard (new customers, orders,
revenue, repeat orders, recovered carts, bookings, event requests,
referrals, wallet use and where orders came from; **Download CSV**), the
occasion calendar, product-review moderation and the city/occasion landing
pages.

- **WhatsApp** (MSG91): order, delivery and booking updates go to everyone;
  offers, cart reminders and occasion nudges only to people who opted in,
  each with an unsubscribe link. Register the templates in
  `deploy/whatsapp_templates.md` with Meta via MSG91.
- **Reviews**: only customers whose order was delivered can review a
  product; stars show on product cards and in Google results
  (`aggregateRating`).
- **Pages for search**: `/artists/<slug>` for every verified artist (they
  set their city in their profile) and `/mehndi/<slug>` landing pages
  written in Admin → Growth; all are in `/sitemap.xml`.
- **Referrals and wallet**: each customer's code is on `/shop/wallet`. A
  friend who joins with it gets ₹50 off their first shop order; the referrer
  gets ₹50 wallet credit once that order is delivered and the return window
  has passed without a return. Credit lasts 180 days and is used at checkout
  (amounts and validity are in Settings).
- **Attribution**: UTM tags, Google/Meta click ids and `?ref=` codes are
  kept from the landing page and stored on the customer (first visit) and on
  each order, booking and event request (latest visit).
- **Server-side purchases**: with `META_PIXEL_ID` + `META_CAPI_TOKEN` and/or
  `GA4_MEASUREMENT_ID` + `GA4_API_SECRET`, each confirmed shop order is
  also sent from the server (Meta Conversions API, GA4 Measurement
  Protocol) for customers who accepted analytics cookies. The order id is
  the event id on both sides, so the browser and the server count once.

### Admin team, audit log and notes

Admin → **Team** (owners) adds admins by phone with one of three roles:

| Role | Can |
|---|---|
| owner | everything, including Settings, the team and the audit log |
| ops | orders, shipping, returns and refunds, payments, products, artists and KYC, bookings, growth |
| support | read-only, plus order notes, approving/rejecting returns, answering failed deliveries, moderating reviews and reports |

The API enforces this for every admin request (`app/core/permissions.py`);
existing admins are owners. Admin → **Audit Log** lists every change, every
refused attempt and every export, with the request id that matches the
server logs. Shop orders and event requests have internal **Notes**.

### Your data (DPDP Act)

Customers and artists can download their data and delete their account
from their profile page. Deleting anonymises the person (name, phone,
photos, addresses, ID and bank details, chat messages) and signs them out;
orders with a GST invoice keep their billing details for the statutory
period, and accounts with an open booking or order can't be deleted until
it's finished. Consent changes (marketing, analytics, deletion) are kept as
evidence. The daily `privacy.retention` job removes OTP codes, old rate-limit
counters, finished jobs, old webhook payloads, read notifications older than
a year and carts untouched for 90 days.

### Media and CDN

Public uploads are stored as WebP (turned upright, at most 4000 px, with
EXIF and location data removed); KYC documents are kept exactly as
uploaded and stay private. Large catalogue photos get a 1600 px display
copy plus a full-size zoom copy. Media files are served with
`Cache-Control: public, max-age=31536000, immutable` (random names are
never reused; fixed names get a day).

To put a CDN in front: with S3, point a CloudFront or Cloudflare host at
the bucket and set `S3_PUBLIC_BASE_URL` to it (uploads already carry the
cache headers and content type). Without S3, proxy the API domain through
Cloudflare and add a cache rule for `/media/*` (respecting origin headers);
`/media/kyc/*` is never cached (`private, no-store`).

### Scaling switches

What to change, in order, when traffic grows (none are needed at launch):

1. **Bigger server** for the one-box Compose stack - Postgres, API and
   worker share it comfortably to tens of thousands of orders a month.
2. **More API workers**: raise `--workers` in `deploy/docker-compose.yml`
   (about 2 per CPU core). Rate limits and the job queue live in Postgres,
   so they hold across workers.
3. **More background workers**: `docker compose up -d --scale worker=3`;
   jobs are claimed with `SKIP LOCKED`, so several never run the same one.
4. **Managed Postgres** (e.g. AWS RDS, DigitalOcean): point `DATABASE_URL`
   at it, drop the `db` service, and keep the nightly backups as a second copy.
5. **Media on S3 + CDN** (above), so app servers can be replaced or added freely.
6. **Watch the slow-request warnings** (`"msg": "slow request"` in the API
   logs) and Sentry performance (`SENTRY_TRACES_SAMPLE_RATE=0.1`) before
   adding indexes or caching.
7. **PostGIS** for artist search once there are thousands of artists (see
   "Known limitation" below).

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
  `<PUBLIC_API_URL>/shop/feed.csv` as a scheduled product feed. Optionally
  set the server-side purchase keys (`META_PIXEL_ID`, `META_CAPI_TOKEN`,
  `GA4_MEASUREMENT_ID`, `GA4_API_SECRET`).
- **Team:** add your ops and support people in Admin → Team rather than
  sharing the owner login.
- **Messaging:** `MSG91_WHATSAPP_NUMBER` and the approved WhatsApp templates.

## What's stubbed vs. production-ready

See `backend/README.md` for the full table (OTP/SMS, Razorpay, PostGIS,
ML design-matching, file storage, background jobs) — every stub is a
config change away from the real thing, not a rewrite.

## Known limitation from setup

PostGIS wasn't installed alongside this Postgres instance, so nearby-artist
search uses plain-SQL Haversine distance instead — accurate enough at
city scale. Install the PostGIS extension later if the artist count grows
large enough that this becomes a real query-performance bottleneck.
