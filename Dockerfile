# syntax=docker/dockerfile:1

FROM python:3.13-slim-trixie AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

FROM base AS build
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# run checks + tests inside docker: docker build --target test .
FROM build AS test
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-groups
COPY tests ./tests
CMD ["sh", "-c", "uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest"]

FROM base AS production
# uid 1000 so it can read a maildir owned by the (uid 1000) mail user
RUN useradd --system --create-home --uid 1000 feeds
COPY --from=build --chown=feeds:feeds /app /app
USER feeds
ENV PATH="/app/.venv/bin:$PATH" \
    NEWSLETTER_MAILDIR=/mail \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]
CMD ["python", "-m", "newsletter_feeds"]
