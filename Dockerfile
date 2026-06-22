FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# Cache dependencies without the editable project (source not copied yet).
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_backend ./garda_ai_backend
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh
# Now install the project itself.
RUN uv sync --frozen --no-dev
RUN chmod +x docker-entrypoint.sh
EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
