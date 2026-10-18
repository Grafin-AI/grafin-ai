FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY grafin_ai_sim ./grafin_ai_sim
RUN uv sync --frozen --no-dev
# LOCAL-ONLY (docker compose convenience). Needs GRAFIN_INGEST_TOKEN + GRAFIN_INGEST_URL and the
# Trans CSVs mounted (set GRAFIN_DATA_DIR). NEVER deployed to production.
RUN useradd --system --uid 1001 grafin
USER grafin
ENV UV_CACHE_DIR=/tmp/uv-cache
CMD ["uv", "run", "--no-sync", "grafin-sim"]
