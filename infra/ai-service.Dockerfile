# syntax=docker/dockerfile:1
# Private Python compute service (CPU inference). Build context: repository root.
#   docker build -f infra/ai-service.Dockerfile --target test .     # run Python tests in Linux
#   docker build -f infra/ai-service.Dockerfile -t vietdoc-ai-service:dev .
# No model weights, datasets or secrets are copied: models come from a read-only volume.

FROM python:3.12.15-slim-bookworm AS deps
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# Dependency layer: rebuilt only when pyproject.toml changes.
COPY pyproject.toml ./
RUN mkdir -p src/vietdoc && touch src/vietdoc/__init__.py \
 && pip install ".[serve]" \
 && pip uninstall -y vietdoc && rm -rf src

FROM deps AS base
COPY src ./src
COPY specs/contracts ./specs/contracts
RUN pip install --no-deps . && rm -rf build src/*.egg-info
ENV VIETDOC_CONTRACTS_DIR=/app/specs/contracts

FROM base AS test
RUN pip install ".[test]"
COPY tests ./tests
COPY docs/design/v1/examples ./docs/design/v1/examples
# Data rendering has its own pinned environment; do not collect its Pillow tests here.
RUN python -m pytest -q -p no:cacheprovider \
    tests/unit/pipeline tests/unit/ml tests/contract tests/architecture tests/integration/api

FROM base AS runtime
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /models /attempts \
 && chown app:app /attempts
ENV VIETDOC_HOST=0.0.0.0 \
    VIETDOC_PORT=8090 \
    VIETDOC_MODELS_DIR=/models \
    VIETDOC_ATTEMPTS_DIR=/attempts \
    LOG_LEVEL=INFO
USER app
EXPOSE 8090
# Liveness only: readiness (/health/ready) stays 503 until a pipeline and release exist.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/health/live', timeout=2).status == 200 else 1)"]
CMD ["python", "-m", "vietdoc.entrypoints.api"]
