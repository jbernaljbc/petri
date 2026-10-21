# Petri: Python 3.13 + uv, unprivileged user. Run by hand with `docker compose run`.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app

# dependencies first, so changing the code doesn't reinstall them
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd -m -u 1000 petri
USER petri
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["petri"]
