# BioVault Deployment Guide

Recommended path for a shareable hackathon demo:

| Approach | Platform | Why |
|---|---|---|
| **Unified (recommended)** | [Vercel Services](https://vercel.com/docs/services) | One project, one URL — frontend + FastAPI backend from the repo root [`vercel.json`](../vercel.json) |
| **Split (alternative)** | Vercel frontend + [Render](https://render.com) backend | Long-running FastAPI + SQLite on a normal web service if you prefer not to use Vercel Services |

Both paths are demo-only. SQLite persistence is not production-ready and may reset on redeploy — users seed data from the UI.

---

## Prerequisites

- GitHub repo connected to Vercel
- For the split path only: GitHub repo also connected to Render

---

## 1. Unified deploy on Vercel (recommended)

This repo ships a root [`vercel.json`](../vercel.json) that defines two services in one project:

| Service | Root | Role |
|---|---|---|
| `frontend` | `frontend/` | Vite React dashboard |
| `backend` | `backend/` | FastAPI permission engine |

Public routing:

- `/api/*` → backend (path stripped to `/health`, `/seed`, etc.)
- everything else → frontend SPA

The frontend uses `/api` as its API base in production automatically — no cross-origin setup required.

### Steps

1. In Vercel: **Add New → Project** → import this repository.
2. Leave **Root Directory** as `.` (repo root). Do **not** set it to `frontend/`.
3. Vercel reads [`vercel.json`](../vercel.json) at the repo root and builds both services. The backend uses [`backend/pyproject.toml`](../backend/pyproject.toml) for Python dependencies (Vercel prefers this over `requirements.txt`).
4. Deploy. No environment variables are required for the basic demo.
5. Open your deployment URL (e.g. `https://biovault.vercel.app`).
6. Click **Seed / Reset Demo** once — that calls `POST /api/seed`.

### How routing works

```
Browser  →  https://your-app.vercel.app/
              │
              ├─ /api/health     →  backend service  →  FastAPI /health
              ├─ /api/seed       →  backend service  →  FastAPI /seed
              └─ / (and /*)      →  frontend service →  Vite static build
```

The backend service includes a path transform so FastAPI receives `/health`, not `/api/health`. See the `routes` block under `backend` in [`vercel.json`](../vercel.json).

### Local unified dev (optional)

With Vercel CLI 48.1.8+:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cd ..
vercel dev
```

Or use the separate local servers in [§4 Local verification](#4-local-verification) below.

### SQLite note (unified path)

On Vercel serverless, the filesystem is ephemeral. Demo data may not survive cold starts or redeploys. Re-click **Seed / Reset Demo** when the artifact list is empty — expected for hackathon demo use.

### Optional environment variables (unified path)

Usually not needed. Override only if you have a specific reason:

| Variable | Where | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | frontend service | Override production API base (default: `/api`) |
| `BIOVAULT_DB` | backend service | Override SQLite path |
| `DEMO_ALLOW_ALL_CORS` | backend service | Leave unset / `false` |

---

## 2. Split deploy — Render backend + Vercel frontend (alternative)

Use this if Vercel Services is unavailable on your account, or you want a long-running backend process that matches local `uvicorn` behavior.

Deploy the backend first — you need its public URL for the frontend env var.

### 2a. Backend on Render

#### Option A — Blueprint (`render.yaml`)

1. In Render: **New → Blueprint** → connect this repository.
2. Render reads [`render.yaml`](../render.yaml) at the repo root:
   - **Root directory:** `backend`
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check:** `/health`
3. After the service is created, open **Environment** and set:

   | Variable | Example | Notes |
   |---|---|---|
   | `CORS_ALLOWED_ORIGINS` | `https://your-app.vercel.app,http://localhost:5173` | Comma-separated; include Vercel URL **and** localhost if you still develop locally against this API |
   | `DEMO_ALLOW_ALL_CORS` | `false` | Leave `false` unless you need a throwaway open demo |

4. Copy the service URL, e.g. `https://biovault-api.onrender.com`.

#### Option B — Manual web service

1. **New → Web Service** → connect repo.
2. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. Add the same environment variables as above.

#### Demo data

There is no automatic seed on boot. After opening the deployed frontend, click **Seed / Reset Demo** once. That calls `POST /seed` and loads principals, artifacts, and capability grants.

#### SQLite note (Render path)

`biovault.db` lives on Render's ephemeral filesystem. Data survives restarts but may be lost on redeploy. Do not commit `backend/biovault.db` (it is gitignored).

### 2b. Frontend on Vercel (split)

1. **New Project** → import this repository.
2. **Root Directory:** `frontend`
3. **Framework Preset:** Vite (auto-detected)
4. **Build Command:** `npm run build`
5. **Output Directory:** `dist`
6. **Environment variable** (Production + Preview):

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://biovault-api.onrender.com` (your Render URL, no trailing slash) |

7. Deploy.

[`frontend/vercel.json`](../frontend/vercel.json) configures SPA fallback rewrites to `index.html` for client-side routing.

Local reference: [`frontend/.env.example`](../frontend/.env.example).

---

## 3. Environment variables summary

### Unified Vercel deploy

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` in production | Set only to override |
| `BIOVAULT_DB` | `backend/biovault.db` | Optional override |
| `DEMO_ALLOW_ALL_CORS` | unset / `false` | Leave false |

No CORS configuration needed — frontend and API share the same origin.

### Split deploy — frontend (Vercel / local)

| Variable | Local default | Production (split) |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Render backend URL |

### Split deploy — backend (Render / local)

| Variable | Local default | Production (split) |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `localhost:5173`, `localhost:3000` (+ 127.0.0.1) | Vercel URL + optional localhost |
| `DEMO_ALLOW_ALL_CORS` | unset / `false` | `false` |
| `BIOVAULT_DB` | `backend/biovault.db` | optional override |

Reference: [`backend/.env.example`](../backend/.env.example).

**Do not commit secrets.** Demo tokens are minted at seed time and returned in the HTTP response — acceptable for hackathon demo only.

---

## 4. Local verification

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass (includes audit evidence and latency checks).

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Optional: copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_BASE_URL=http://localhost:8000`.

```powershell
cd frontend
npm run build
```

---

## 5. Post-deploy smoke test

1. Open your deployment URL.
2. Click **Seed / Reset Demo** — wait for "Demo seeded…" message.
3. **Step 1:** CEO opens Phase II Readiness Memo → **ALLOW**.
4. **Step 2:** External CRO opens same memo → **DENY** (`missing_capability_grant`).
5. **Step 4:** Revoke Adverse Event Memo → quarantine cascades.
6. Scroll to **Audit Log** → click a row → full `request_id` and structured detail visible.

Quick API check:

```bash
# Unified Vercel deploy
curl https://YOUR-VERCEL-URL/api/health
# {"status":"ok","service":"biovault"}

# Split Render backend
curl https://YOUR-RENDER-URL/health
# {"status":"ok","service":"biovault"}
```

---

## 6. Troubleshooting

### Unified Vercel deploy

| Symptom | Likely cause | Fix |
|---|---|---|
| Import fails or only frontend builds | Root Directory set to `frontend/` | Re-import with Root Directory `.` (repo root) |
| API 404 on `/health` | Hitting frontend instead of backend | Use `/api/health`, not `/health`, on the public URL |
| Empty users/artifacts | No seed yet | Click **Seed / Reset Demo** |
| Data gone after redeploy | Ephemeral SQLite on serverless | Re-seed demo — expected for hackathon demo |
| 401 on artifact reads | Seed not run or stale tab | Re-seed demo; ensure bearer tokens from seed are in client state |

### Split deploy (Render + Vercel)

| Symptom | Likely cause | Fix |
|---|---|---|
| Frontend cannot reach backend | Wrong `VITE_API_BASE_URL` | Set to Render URL in Vercel env; redeploy frontend (Vite bakes env at build time) |
| Browser CORS error | Backend does not allow Vercel origin | Add `https://your-app.vercel.app` to `CORS_ALLOWED_ORIGINS` on Render; save and wait for restart |
| Empty users/artifacts | No seed yet | Click **Seed / Reset Demo** on the frontend |
| First request very slow | Render free tier cold start | Wait ~30s, refresh, try again |
| 401 on artifact reads | Seed not run or stale tab | Re-seed demo; ensure bearer tokens from seed are in client state |
| Data gone after redeploy | Ephemeral SQLite on Render | Re-seed demo — expected for hackathon demo |

---

## Security reminder

These deployment paths are for **hackathon / judge demo** use. Capability-token auth, grant authority, redaction, lineage, and revocation logic are unchanged — but hardcoded Fernet keys, plaintext seed tokens, and SQLite are not production-ready. See [README.md](../README.md) residual limitations.
