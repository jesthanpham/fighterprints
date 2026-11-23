FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv
WORKDIR /app

# dependencies first, so code changes don't reinstall everything
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    UFC_DATABASE_URL="postgresql://ufc:ufc@postgres:5432/ufc" \
    UFC_DB_HOST="postgres" \
    UFC_DB_PORT="5432" \
    DAGSTER_HOME="/dagster_home"

# build the dbt manifest Dagster reads (parsing needs no database)
RUN dbt parse --project-dir dbt --profiles-dir dbt && mkdir -p /dagster_home
