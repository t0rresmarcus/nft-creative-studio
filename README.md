# NFT Creative Studio

A local web studio for NFT artists: edit artwork, stack trait layers, generate unique collections, batch-process photos, validate the drop, and export marketplace files.

The product plan lives in `docs/`. This repository is the application described there. Contract deployment, scheduled triggers, and hosted GPU models are intentionally not included. Image work that does not need a model runs in-process. Point `AI_ENDPOINT` at a ComfyUI-style worker when you have one.

## Run it

From the repository root, in two terminals:

```bash
cd apps/api
uv venv --python 3.12 .venv
uv pip install -r requirements-dev.txt --python .venv/bin/python
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000 and sign in with the seeded demo:

- email `demo@nftstudio.local`
- password `demo-studio-123`

The demo project is **Signal Portraits**. Plan a collection, render it, then download the ZIP.

`make test` runs the API suite. `make api` and `make web` start the two processes after dependencies are installed.

Docker Compose (`docker compose up --build`) starts Postgres, Redis, the API, a job worker, and the web app. The default local path uses SQLite and an in-process worker, so Docker is optional.

## What the studio does

| Area | Behavior |
| --- | --- |
| Accounts | Email sign-in, four plans, credit balance, encrypted Pinata JWT |
| Projects | Multiple projects, roles (owner, editor, reviewer), notes, approvals |
| Library | Image upload, SHA-256 storage, thumbnails, signed URLs |
| Editor | Crop, resize, rotate, color, undo/redo, server-side save, version history |
| Traits | Layers, drag order, weights, exact counts, exclude/require rules, sample set, templates |
| Generator | Weighted or exact-count generation, deterministic seeds, duplicate refusal, single-token regenerate |
| Automation | Visual recipes, conditions, seeded ranges, dry run, retries |
| Metadata | ERC-721 and Metaplex JSON, CSV, description templates |
| Publish | QA report, ZIP (images, JSON, CSV, provenance), local content IDs or Pinata |
| AI | Corner background removal, optional remote/rembg cutout, enhance, inpaint, variations |

Large files stay on disk (or in the Docker volume), not in Postgres. The same seed, trait configuration, and source hash reproduce the same batch output.

## Configuration

Copy `.env.example` to `.env` if you want to override defaults. Useful variables:

- `DATABASE_URL` — SQLite by default, Postgres in Compose
- `SECRET_KEY` — signs sessions, file URLs, and the Pinata secret
- `AI_ENDPOINT` — optional HTTP worker implementing `/remove-background`
- `PUBLIC_BASE_URL` — used when a collection is content-addressed locally
- `CELERY_ENABLED` and `REDIS_URL` — optional Celery broker; otherwise `python -m app.worker` polls the jobs table

Plans can be switched from the account page while `ALLOW_PLAN_SWITCH=1`. That is a local stand-in for billing, not a payment integration.
