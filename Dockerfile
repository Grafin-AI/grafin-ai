FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_ingest ./garda_ai_ingest
RUN uv sync --frozen --no-dev
# --no-sync: the venv is already built above; skip uv's startup resync for faster starts.
CMD ["uv", "run", "--no-sync", "garda-ingest"]
