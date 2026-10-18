FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_scoring ./garda_ai_scoring
RUN uv sync --frozen --no-dev
EXPOSE 8000
# --no-sync: the venv is already built above; skip uv's startup resync for faster cold starts.
CMD ["uv", "run", "--no-sync", "uvicorn", "garda_ai_scoring.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
