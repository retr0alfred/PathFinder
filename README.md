# Lodestar

**Learning is a dependency graph, not a search result.**

Lodestar takes a goal in plain English, measures what you actually know with a
short placement check, works out the shortest valid route to that goal, packs it
into the hours you really have each week, attaches a traceable reason to every
step, and re-plans the moment anything changes — using only real, HTTP-verified,
almost entirely free resources.

**Ask it for a subject it has never seen and it builds one.** It ships knowing
260 skills across 16 subjects. Ask for something outside that and it says so
plainly, then designs a prerequisite structure for the subject, searches the
live web for material, fetches every page before using it, and merges the result
into the same graph the planner already works on. Nothing downstream knows the
difference.

**Live:** frontend on Vercel, API on Render. Both free tiers.

- **Web — <https://path-finder-cyan.vercel.app>**
- **API — <https://lodestar-api-qvzn.onrender.com>** · interactive docs at `/docs`

The API sleeps after 15 idle minutes; the first request after that takes about a
minute to wake it. Open it once before a demo.

---

## You need one free API key

Lodestar's language layer is **OpenRouter, and only OpenRouter**, restricted to
models that cost exactly nothing.

```
OPENROUTER_API_KEY=sk-or-v1-...
```

Get one at **[openrouter.ai/keys](https://openrouter.ai/keys)** — free, and no
card is required.

**"Free" is enforced by the code, not trusted.** The model list is discovered
live from OpenRouter's own catalogue and filtered to entries whose prompt *and*
completion price are exactly zero. Every response is checked for a reported
cost, and any model that charges is retired immediately for the rest of the
process. A configured `OPENROUTER_MODEL` is ignored unless the catalogue agrees
it is free, so the setting cannot start a bill by accident. At startup the
server logs how many free models it found — 21, on the last deploy.

**There is no second AI provider in production.** No local model, no hosted
fallback. `LLM_PROVIDER=openrouter` constructs one provider and never imports
another. When OpenRouter is throttled — free models are rate-limited without
warning — the product does not error. Every reason, question and reply already
has a deterministic form computed by ordinary Python; the model only ever
rephrases it. So a throttled key costs you fresher wording, never correctness
and never an outage.

---

## Deploying it

Two services, both free, roughly ten minutes.

### 1. API → Render

The repo contains [`render.yaml`](render.yaml), so Render configures itself.

1. Sign up at [render.com](https://render.com) — GitHub login, no card.
2. **New → Blueprint** → pick this repo → Render reads the Blueprint and fills
   in service type, Docker runtime, free plan, region and health check.
3. It prompts for two values:
   - `OPENROUTER_API_KEY` — your key from above
   - `CORS_ORIGINS` — your Vercel URL; leave blank on the first pass and set it
     after step 2
4. Deploy. First build takes a few minutes, mostly baking the embedding model
   into the image.

Check `https://<your-service>.onrender.com/health` — it should report
`llm_provider: openrouter`, `graph_nodes: 260`, `catalog_size: 707`.

### 2. Frontend → Vercel

1. Sign up at [vercel.com](https://vercel.com) with GitHub.
2. **Add New → Project** → import this repo.
3. **Root directory: `frontend`** — it defaults to the repo root, and the build
   fails if you leave it there.
4. Environment variable `VITE_API_BASE` = your Render URL.
5. Deploy, then put the resulting `*.vercel.app` URL into Render's
   `CORS_ORIGINS` and redeploy the API.

[`frontend/vercel.json`](frontend/vercel.json) supplies the SPA rewrite and
asset caching, so there is nothing to configure in the dashboard.

Preview deployments work without touching anything — the API already allows any
`*.vercel.app` origin by regex.

### What the free tier actually means

| | |
|---|---|
| Idle timeout | Render spins the API down after **15 minutes** with no traffic |
| Wake | About **one minute**. The frontend retries rather than reporting a failure |
| Disk | **Ephemeral** — reset on every redeploy *and* every spin-down |
| Database | Free Postgres. This is what actually survives a spin-down |
| Cost | ₹0. With no card on file Render suspends rather than bills |

The ephemeral disk is why **the discovered-subject corpus is committed to the
repo** rather than generated at runtime: the 11 pre-built subjects live inside
the image, so they open instantly and cannot be lost.

Everything written *after* deploy goes to Postgres instead of that disk —
learner profiles, mastery, plan versions, and any subject a visitor builds.
Before this, a learner who waited two minutes for a new subject lost it at the
next quiet quarter-hour, and so did everyone after them.

**Where discovered subjects are stored is decided by the database, not by a
flag you have to remember.** `GENERATED_STORE=auto` resolves to the database
whenever `DATABASE_URL` is not SQLite, and to a directory of inspectable JSON
when it is. So local development is unchanged — `data/generated/`, greppable,
deletable with `rm -r` — and a deployment persists without either behaviour
being special-cased.

Render's free Postgres **expires 30 days after creation**. For a longer-lived
deployment, point `DATABASE_URL` at a free tier that does not expire —
[Neon](https://neon.tech) or [Supabase](https://supabase.com) — which is a
one-variable change and needs no code edit.

---

## Running it locally

```bash
git clone https://github.com/retr0alfred/PathFinder.git
cd PathFinder
start.bat
```

`start.bat` finds Python and Node, creates the virtual environment, installs
dependencies **only when `requirements.txt` actually changed**, writes `.env`,
and — the first time only — asks for your OpenRouter key. Pressing Enter skips
it, and the app still runs. It then prepares the database, downloads the
sentence-embedding model once (~130 MB), starts both servers, waits for the
health check and opens a browser.

| Command | Effect |
|---|---|
| `start.bat` | Normal start |
| `start.bat --reset` | Wipe venv, node_modules and the database, rebuild |
| `start.bat --backend` | API only |
| `start.bat --no-browser` | Do not open a browser |
| `./run.sh` | macOS / Linux equivalent, same flags |

Locally you have one option production does not: setting `LLM_PROVIDER=ollama`
runs a small model on your own machine with no key and no quota. It is slower —
about 43 s to read an intake message versus ~3 s hosted, which is precisely why
production does not use it — but it cannot run out. `LLM_PROVIDER=mock` needs
nothing at all and answers from templates.

It refuses to start when something already holds port 8000, rather than
reporting a stranger's server as healthy.

Web `http://localhost:5173` · API `http://127.0.0.1:8000` · docs `/docs`

---

## What runs where

Nothing in the critical path needs a hosted service except phrasing.

| Job | How it is done | Needs the network? |
|---|---|---|
| Search and matching | `bge-small-en-v1.5` locally through ONNX, 384-dim | No — baked into the image |
| Sequencing, scheduling, gap analysis | Ordinary Python: graph traversal and bin-packing | No |
| Deciding whether a subject is covered | Two measured signals, no model | No |
| Placement questions | A bank of 236 items, generated once and committed | No |
| Explanations | Provenance computed as data, rendered from a template | No |
| Assistant replies | Rule-based from your own plan rows, phrased by the model | OpenRouter |
| **Designing a new subject** | The model proposes structure only — never a fact, never a link | OpenRouter |
| **Finding material for it** | Live search, then every page fetched and checked | Yes, once per subject |

Everything above the bold rows works with the model entirely unavailable.

---

## The idea in one paragraph

A learner describes a goal. Lodestar resolves it to node(s) in a skill
dependency graph, measures what they know, computes the gap as a graph
operation, orders that gap topologically so nothing is ever taught before its
prerequisite, binds each skill to a real verified resource, packs it into the
hours they actually have, and attaches a reason to every step. Change an
answer, a budget or a deadline and it re-plans and shows what moved.

**Deterministic code does the reasoning; the model only handles language.**
Every planning decision is ordinary Python. That is why the output is
explainable rather than asserted, and why it stays correct when the model is
throttled.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  React 18 + TypeScript + Vite            → Vercel               │
│  Intake · Diagnostic · Path(+graph) · Dashboard · Chat          │
└────────────────────────────┬────────────────────────────────────┘
                             │ JSON over HTTP, typed contracts
┌────────────────────────────▼────────────────────────────────────┐
│  FastAPI                                  → Render (Docker)     │
│  intake · diagnostic · path · dashboard · adapt · topics · usage│
├─────────────────────────────────────────────────────────────────┤
│  core/  skill_graph · planner · retrieval · mastery · questions  │
│         explain · expansion · websearch · store · placement      │
├─────────────────────────────────────────────────────────────────┤
│  llm/   openrouter (production)  ·  ollama · mock (local only)   │
├─────────────────────────────────────────────────────────────────┤
│  data/            the curated seed, committed                    │
│  data/generated/  11 discovered subjects, committed              │
│  SQLite           learners, mastery, plan versions (ephemeral)   │
└─────────────────────────────────────────────────────────────────┘
```

### The algorithm

`required → gap → order → bind → pack`

**required** — `ancestors_closure(goals) | goals`. Pure reverse reachability.

**gap** — `{n in required : mastery(n) < 0.7}`. Unmeasured counts as zero, and a
self-report is capped at 0.4, so nothing leaves the path on a claim alone.

**order** — a topological sort of the gap. This is the step a similarity-ranked
list cannot produce: it answers "what am I allowed to start now", not "what is
relevant". Ties break deterministically, so identical input yields a
byte-identical path.

**bind** — hard filters (format, cost, language) then a weighted score. Rank 1
is bound; ranks 2–3 become the swap options.

**pack** — greedy first-fit into weeks at the learner's real capacity. No week
exceeds `hours_per_week`, and no skill is placed before any prerequisite's week.

The planner is pure: no database, no model, no I/O. That is what makes its
correctness properties testable.

### When the goal is not in the graph

Nearest-neighbour over a closed set cannot say "I don't know this" — it once
turned *quantum computing* into a programming topic and handed over a confident,
wrong plan.

Coverage is now decided first, by two cheap signals: similarity calibrated
against the graph's own name-match distribution, and IDF-weighted lexical
familiarity. Together they are right on **17 of 18** check goals in about a
third of a second with no model call. When they are wrong, the interface shows
which skill was matched and offers a one-click override — a wrong guess a person
can see and overrule beats a confident one they cannot.

For a genuinely new subject, `POST /api/topics/build` runs a background job:

```
1. DESIGN     the model proposes 8-12 skills and their dependencies —
              structure only. A prerequisite may only reference an EARLIER
              index, so a cycle cannot be expressed, not merely rejected
2. SEARCH     one live query per skill, from the skill's own keywords
3. VERIFY     every URL fetched; non-2xx, non-HTML and bot walls discarded;
              title, provider, format and cost read off the page that answered
4. EMBED      new skills and resources vectorised locally
5. MERGE      written to data/generated/ and layered on the graph; the seed is
              never modified, and a node with an unresolvable prerequisite is
              dropped rather than breaking the graph for everyone
6. QUESTIONS  placement questions written in the background afterwards
```

About two minutes, once. The result is cached and shared.

### Subjects must not leak into each other

Asked for business studies, an earlier build produced Python questions. Three
causes, the first embarrassing: the syllabus prompt literally invited
prerequisites *"from other subjects (the mathematics a topic requires, for
instance)"* — reasonable for quantum computing, a licence to make everything
technical.

Every discovered skill now carries its **subject** and three independent domain
flags — `technical`, `quantitative`, `practical` — set when the syllabus is
designed and read downstream. Question generation asks a quantitative skill to
work something out and a studied one to explain, in its own subject. Search
queries stay inside the subject. A skill can be several axes at once, or none.

Rebuilt, business studies gives twelve real business skills, tested on the 4Ps,
SWOT, NPV and supply chains. *The French Revolution* builds 12 skills and 26
verified resources with **zero** steps mentioning code.

### Where the AI is, and where it deliberately is not

| Decision | Made by | Why |
|---|---|---|
| Goal → skill nodes | Local embedding retrieval, then constrained selection from a fixed shortlist | A model alone invents nodes that do not exist |
| Is this subject covered? | IDF-weighted familiarity + calibrated similarity | Faster and more accurate than asking a model |
| New subject → structure | Schema-constrained generation, then structural validation | The one thing only a model can propose; the code decides what is admissible |
| New subject → material | Live search, then HTTP verification of every page | A model asked for links invents them |
| Ordering, scheduling, scoring | Pure deterministic code | Reproducible, explainable, correct with no model |
| Wording | The model, within a latency budget | Language is the only thing delegated |

---

## API contract

| Endpoint | Purpose |
|---|---|
| `GET /health` | status, provider, embedder, catalogue size, graph size, question bank |
| `GET /api/usage` | which model is answering, requests, tokens, cost |
| `GET /api/topics/coverage` | is this goal already taught? |
| `POST /api/topics/build` | start building a subject; returns immediately |
| `GET /api/topics/build` | progress: stage, detail, fraction, elapsed |
| `POST /api/intake/message` | assistant reply + partial profile + `ready` |
| `POST /api/intake/commit` | creates the learner, resolves the goal |
| `GET /api/diagnostic/next/{lid}` | next question, or `{done: true}` |
| `POST /api/diagnostic/answer` | grades, updates mastery, returns confidence |
| `POST /api/path/generate/{lid}` | builds a new path version |
| `GET /api/path/{lid}?version=` | items, weeks, provenance, per-week load |
| `POST /api/path/whatif` | recomputed at a hypothetical capacity, never persisted |
| `POST /api/path/event` | applies one of seven events → new version + diff |
| `POST /api/chat/{lid}` | answers about this learner's own plan |
| `GET /api/dashboard/{lid}` | progress, hours, mastery spread, next actions |
| `GET /api/graph/{lid}` | nodes and edges annotated with mastery |

Every model-shaped response is schema-validated before it leaves the server. On
failure: retry once with the error appended, then fall back deterministically
with `llm_degraded: true`. Never a 500.

### The seven adaptation events

| Event | Effect |
|---|---|
| `milestone_failed` | Lower mastery across the block; re-open those steps |
| `too_easy` | Raise mastery to 0.8; drop the step; schedule pulls forward |
| `too_hard` | Reinstate the groundwork it assumed, ahead of it |
| `behind_schedule` | Repack weeks; return scope-reduction options |
| `goal_changed` | Re-resolve; preserve mastery for overlapping work |
| `resource_disliked` | Rebind to the rank-2 resource |
| `completed_item` | Mark done; raise mastery; advance progress |

---

## The data

| | Ships in the image | |
|---|---|---|
| Skill graph | **260 nodes**, 16 subjects | 152 curated + 108 discovered |
| Catalogue | **707 resources**, every URL HTTP-verified | 426 curated + 281 discovered |
| Question bank | **236 items** | 144 curated + 92 generated |
| Pre-built subjects | **11** | quantum computing, business studies, the French Revolution, organic chemistry, astrophysics, Roman history, cell biology, sheet music, astronomy, quantum physics, and more |

The curated catalogue is built by propose-then-verify: a model suggests
candidates, then every URL is fetched and **every non-2xx entry discarded**. 856
candidates became 426 verified resources. A hallucinated link cannot survive
that, which is the point. Discovered resources go through the same gate at
build time, and carry no invented rating.

## Evaluation — measured, not asserted

`python -m scripts.evaluate` runs the planner against 20 synthetic personas with
hand-written gold paths. Targets are fixed in the harness and never adjusted to
match a result.

| Metric | Result | Target |
|---|---|---|
| Prerequisite-order violations | **0.0%** | 0% |
| Goal-skill coverage | **100.0%** | ≥95% |
| Redundancy | **0.0%** | 0% |
| Path length vs gold | **0.97×** | 0.80–1.30× |
| Free-only compliance | **100.0%** | 100% |
| Grounding (resources in catalogue) | **100.0%** | 100% |
| p95 warm path generation | **3.8 ms** | < 2000 ms |

```bash
cd backend && .venv/Scripts/python -m pytest        # 243 tests, no network, no key
cd frontend && npm run build                        # strict TypeScript, zero errors
```

---

## Repository layout

```
.
├── Dockerfile  render.yaml           the API deployment
├── start.bat  run.bat  run.sh  .env.example
├── backend/
│   ├── app/
│   │   ├── main.py config.py db.py models.py schemas.py
│   │   ├── routers/  intake diagnostic path adaptation chat dashboard
│   │   │             graph topics usage
│   │   ├── core/     skill_graph mastery retrieval planner explain adapt
│   │   │             embeddings questions expansion websearch store placement
│   │   └── llm/      base openrouter ollama mock prompts
│   ├── data/           skills.json courses.json questions.json *_embeddings.npy
│   │   └── generated/  the 11 discovered subjects
│   ├── scripts/        build_* harvest verify check_links seed evaluate journeys
│   └── tests/
├── frontend/
│   ├── vercel.json
│   └── src/            pages/ components/ lib/
└── deploy/README.md
```

---

## Known limitations

An honest account, because the boundaries are as informative as the features.

- **The free API tier sleeps.** Fifteen idle minutes and the next visitor waits
  about a minute. Nothing fixes this on a free plan; hitting the URL a few
  minutes before a demo does.
- **The free database expires after 30 days.** Render's free Postgres is time-
  limited, not size-limited. Moving to Neon or Supabase is a `DATABASE_URL`
  change and nothing else.
- **A cold wake can still outlast the retry window.** The frontend retries for
  about thirty seconds before reporting a failure, which covers a normal wake
  but not a slow one on top of a fresh build.
- **A free hosted model is a courtesy, not a guarantee.** OpenRouter's free tier
  is throttled without warning and publishes no daily allowance, so the usage
  panel shows real counts and states that the cap is unpublished rather than
  drawing a progress bar against a number nobody stated.
- **A discovered subject is only as good as the model's idea of it.** Structure
  is validated — acyclic, in range, deduplicated — but nobody checks that
  "Quantum Circuit" really depends on "Quantum Gates".
- **The subject classification is the model's opinion.** Whether business
  studies is "quantitative" is a judgement made once, at build time, and it
  shapes both searches and questions.
- **Coverage detection is 17/18 on eighteen goals** — a validation set, not a
  benchmark. The override button is the real mitigation.
- **Generated questions are not position-balanced** the way the committed 144
  are.
- **English only.** The language filter is enforced, but the catalogue is
  entirely `en`.
- **The skill graph is hand-authored and opinionated.** 152 curated nodes and
  255 edges reflect one person's judgement about what depends on what.

---

## Attribution

Built for the AMPlified Round 2 prototype brief, *AI-Powered Personalized
Learning Path Recommender*. The skill graph, catalogue pipeline, planner and
evaluation harness are original work; learning resources are third-party and
linked, never rehosted.

Designed and built end to end, solo, by **Alfred Mathew**.
