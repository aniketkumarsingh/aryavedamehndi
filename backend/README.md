# AryaVeda Mehndi — Backend (FastAPI)

## One-time setup

Already done for this machine — the local `postgres` superuser password is
the same one used by the `univest-redesign-studio-main` project's backend
`.env` (`DATABASE_URL=postgresql+asyncpg://postgres:<password>@127.0.0.1:5432/...`).
Role `aryamehndi_app` / password `changeme` and database `aryamehndi` were
created via `setup_db.sql`, migrations are applied, and starter data is
seeded. Skip to **Run the dev server** below.

To redo this from scratch on another machine:

1. Create the database role + database (you'll be prompted for the
   Postgres superuser password):

   ```
   "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -f setup_db.sql
   ```

   This creates role `aryamehndi_app` / password `changeme` and database
   `aryamehndi`. Change the password in `setup_db.sql` before running it if
   you'd like a different one — just keep `backend/.env` in sync.

2. Copy the env file and adjust if you changed the DB password above:

   ```
   copy .env.example .env
   ```

3. Create the virtualenv and install dependencies (already done once by
   Claude during this build — re-run only if you recreate the folder):

   ```
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt
   ```

4. Run migrations and seed starter data:

   ```
   venv\Scripts\alembic upgrade head
   venv\Scripts\python seed.py
   ```

## Run the dev server

```
venv\Scripts\uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**Known quirk on this machine:** starting uvicorn from Git Bash sometimes
spawns a second, duplicate process on the *system* Python instead of the
venv one, which then serves stale code after an edit. If a change doesn't
seem to take effect, check for duplicates and kill everything before
restarting:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Select ProcessId, CommandLine
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | % { Stop-Process -Id $_.ProcessId -Force }
```

## Running tests

A dedicated `aryamehndi_test` database (same `aryamehndi_app` role) keeps
tests fully isolated from your dev data — the suite drops and recreates its
schema every run.

One-time setup (already done on this machine):

```
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE aryamehndi_test OWNER aryamehndi_app;"
venv\Scripts\pip install -r requirements-dev.txt
```

Run the suite:

```
venv\Scripts\pytest
```

Covers: OTP auth flow, DPDP consent gating, booking creation + gender
matching + negotiation, favorites, notification pagination, admin
pagination/role-gating, the real-time chat WebSocket (round-trip delivery,
history persistence, auth/participant rejection), and the SSRF/IDOR fixes
from the security audit (reference-image URL validation, payment ownership
checks, negotiation amount bounds).

## What's stubbed for local dev vs. production

| Feature | Local dev | Production |
|---|---|---|
| OTP | printed to the server console (`OTP_DEV_MODE=true`) | real SMS via MSG91 once `MSG91_AUTH_KEY` is set and `OTP_DEV_MODE=false` |
| Razorpay | fake order IDs, signature check auto-passes | real orders/verification once `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are set |
| Nearby-artist search | Haversine distance in plain SQL/Python | swap in PostGIS `ST_DWithin` later for scale — same API shape |
| Design-match scoring | perceptual-hash similarity (`ImageHash`) | swap `app/services/similarity.py` for a CLIP-embedding model for higher accuracy — nothing else changes |
| File storage | local disk under `backend/media/`, served at `/media/...` | set the `S3_*` env vars to switch to S3/R2 automatically |
| Background jobs (OTP send, similarity scoring) | run synchronously in the request | move to Celery + Redis once traffic justifies it |

## Key flows

- **Auth**: `POST /auth/request-otp` → `POST /auth/verify-otp` (creates the
  user on first login, returns a JWT).
- **Booking lifecycle**: `requested → negotiating → confirmed →
  artist_enroute → arrived → in_progress → design_uploaded → completed`,
  with `disputed`/`cancelled` side branches. See `app/models/booking.py`.
- **Payment gate**: `POST /bookings/{id}/payment/order` refuses unless the
  booking is `design_uploaded` *and* the design's `match_status` is
  `auto_matched` or `consumer_confirmed` — payment can't be initiated
  around the design check.
