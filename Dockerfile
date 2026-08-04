FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_sim ./garda_ai_sim
RUN uv sync --frozen --no-dev
# LOCAL-ONLY (docker compose convenience). Needs GARDA_INGEST_TOKEN + GARDA_INGEST_URL and the
# Trans CSVs mounted (set GARDA_DATA_DIR). NEVER deployed to production.
RUN useradd --system --uid 1001 garda
USER garda
CMD ["uv", "run", "--no-sync", "garda-sim"]
