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

**1. Database.** Postgres 17 is already running locally. Create the app's
role + database (you'll be prompted for your `postgres` superuser
password — I didn't set this up automatically since it needs your
credentials):

```
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -f backend\setup_db.sql
```

**2. Backend env + migrations:**

```
cd backend
copy .env.example .env
venv\Scripts\alembic upgrade head
venv\Scripts\python seed.py
```

(The virtualenv and all Python packages are already installed.)

**3. Frontend env** (defaults are already correct for local dev, this step
is optional):

```
cd frontend
copy .env.local.example .env.local
```

(`node_modules` are already installed.)

## Running it

Two terminals:

```
cd backend
venv\Scripts\uvicorn app.main:app --reload --port 8000
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

## What's stubbed vs. production-ready

See `backend/README.md` for the full table (OTP/SMS, Razorpay, PostGIS,
ML design-matching, file storage, background jobs) — every stub is a
config change away from the real thing, not a rewrite.

## Known limitation from setup

PostGIS wasn't installed alongside this Postgres instance, so nearby-artist
search uses plain-SQL Haversine distance instead — accurate enough at
city scale. Install the PostGIS extension later if the artist count grows
large enough that this becomes a real query-performance bottleneck.
