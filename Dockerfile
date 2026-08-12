FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_ingest ./garda_ai_ingest
RUN uv sync --frozen --no-dev
# Runtime needs GARDA_DATABASE_URL and the accounts CSV (mount the data dir + set GARDA_DATA_DIR).
RUN useradd --system --uid 1001 garda
USER garda
# `useradd --system` creates no home dir, so uv's default cache path
# (/home/garda/.cache/uv) is unwritable -> point it at a writable location.
ENV UV_CACHE_DIR=/tmp/uv-cache
# --no-sync: the venv is already built above; skip uv's startup resync for faster starts.
CMD ["uv", "run", "--no-sync", "garda-ingest"]
