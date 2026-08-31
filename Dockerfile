# Lodestar API — container image for Render (free web service, Docker runtime).
#
# Four platform facts drive this file:
#   * Render injects the listening port as $PORT; nothing else is routed,
#   * the filesystem is ephemeral — wiped on redeploy AND on every spin-down,
#     which on the free plan happens after 15 idle minutes,
#   * a cold start should not download anything, because a wake already costs
#     the visitor about a minute, and
#   * the language layer is OpenRouter and only OpenRouter (see LLM_PROVIDER
#     below) — there is no local model in a container and no silent fallback
#     to one.
#
# So the database is created at container start rather than baked in, and the
# embedding model is downloaded at *build* time and cached in the image. The
# skill graph, the verified catalogue, the question bank, the pre-built subject
# corpus and the embedding matrices all ship in the image, which is why a cold
# start needs no network for anything except OpenRouter itself.
#
# Build context is the repository root:
#   docker build -t lodestar .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface

RUN useradd -m -u 1000 user
WORKDIR /app

COPY --chown=user backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user backend/ ./
RUN chown -R user:user /app
USER user

# Download the sentence-embedding model now, so the first request is instant
# and a wake from spin-down does not wait on a 130 MB download.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# The database lives under the writable home directory, not an image layer.
# It does not survive a spin-down; that is a clean reset, not a failure, and
# it is why the demo corpus is committed rather than generated at runtime.
ENV DATABASE_URL=sqlite:////home/user/lodestar.db \
    LLM_PROVIDER=openrouter \
    EMBEDDER=auto \
    LOG_LEVEL=INFO

# Render sets $PORT. The default is only for a local `docker run`.
ENV PORT=10000
EXPOSE 10000

# Seed on every start, because the disk does not survive a spin-down.
CMD ["sh", "-c", "python -m scripts.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
