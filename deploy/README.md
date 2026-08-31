# Deploying Lodestar for zero cost

Frontend on **Vercel**, API on **Render**. No card, no trial clock.

> **Why not Hugging Face Spaces?** An earlier version of this file targeted a
> Docker Space. Hugging Face now gates Docker and Gradio Spaces behind a paid
> plan — *"Static Spaces are free for everyone. Gradio and Docker Spaces run on
> compute and require a paid plan to create."* Only static HTML is free there,
> which cannot host a Python API. Render's free web service does support Docker,
> and with no payment method on file the failure mode is suspension, never a
> bill.

---

## 1. API → Render

[`render.yaml`](../render.yaml) at the repo root is a Blueprint, so Render
configures the service itself.

1. Sign up at [render.com](https://render.com) — GitHub login is fine.
2. **New → Blueprint** → select this repository.
3. Render reads the Blueprint and fills in: web service, Docker runtime, free
   plan, Singapore region, `/health` health check, and every non-secret
   environment variable.
4. It prompts for the two values marked `sync: false`:

| Key | Value |
|---|---|
| `OPENROUTER_API_KEY` | your free key from <https://openrouter.ai/keys> |
| `CORS_ORIGINS` | your Vercel URL — leave blank now, fill in after step 2 |

5. Deploy. The first build takes a few minutes, most of it baking the
   sentence-embedding model into the image so that a cold start needs no
   download.

Verify at `https://<service>.onrender.com/health`:

```json
{"status":"ok","llm_provider":"openrouter","embedder":"bge-small",
 "catalog_size":707,"graph_nodes":260,"graph_tracks":16,"question_bank":236}
```

`GET /api/usage` should show `"chain":["openrouter"]` — one provider, no
fallback — and a non-zero `free_models_available`.

## 2. Frontend → Vercel

1. Import the GitHub repo at [vercel.com](https://vercel.com).
2. **Root directory: `frontend`.** This is the one setting that is not
   inferred, and the build fails without it.
3. Framework preset Vite; build `npm run build`; output `dist`. All
   auto-detected. [`frontend/vercel.json`](../frontend/vercel.json) supplies the
   SPA rewrite and asset cache headers.
4. Environment variable: `VITE_API_BASE=https://<service>.onrender.com`
5. Deploy. Every push to `main` redeploys.

Then set that Vercel URL as `CORS_ORIGINS` on the Render service and redeploy
the API. Preview deployments need no extra configuration — `app/main.py` already
allows any `*.vercel.app` origin by regex.

`VITE_API_BASE` is inlined at build time, so changing it requires a redeploy,
not just a restart.

---

## The free-tier bargain

| | |
|---|---|
| Idle timeout | 15 minutes without traffic → spun down |
| Wake | ~1 minute, with a loading page |
| Disk | Ephemeral: reset on redeploy **and** on every spin-down |
| Instance hours | 750/month — enough to run one service continuously |
| Cost | ₹0. Without a payment method Render suspends rather than bills |

**Two consequences worth designing around, both already handled:**

*The discovered-subject corpus is committed to the repo* rather than built at
runtime. A subject built live on the deployed instance works, and vanishes at
the next spin-down. The 11 pre-built subjects live inside the image, so they
open instantly and permanently.

*Learner profiles reset* on every spin-down, since SQLite lives on that same
ephemeral disk. This is a clean reset rather than a failure. For persistence,
point `DATABASE_URL` at a free hosted Postgres (Supabase or Neon) — SQLModel
makes it a one-variable change.

## Before a demo or judging

- [ ] Hit the API URL a few minutes beforehand so it is awake, not cold.
- [ ] Confirm `/health` reports `llm_provider: openrouter`.
- [ ] Confirm `/api/usage` shows free models available and no retired models.
- [ ] Open the Vercel URL on a phone, on mobile data, in a private window.
- [ ] Run one full journey on the deployed build, not just locally.
- [ ] Put **both** URLs in the README and the submission form.
