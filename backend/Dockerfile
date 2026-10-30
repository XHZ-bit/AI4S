FROM python:3.11.17-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock MANIFEST.in ./
RUN uv sync --locked --no-dev --no-install-project --python /usr/local/bin/python \
    && useradd --create-home appuser
COPY app ./app
COPY scripts ./scripts
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python \
    && mkdir -p /app/data && chown -R appuser:appuser /app/data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
