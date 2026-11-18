# syntax=docker/dockerfile:1
# Offline training/spike environment, separate from the inference image.
#   docker build -f infra/ai-train.Dockerfile -t vietdoc-ai-train:dev .                                  # CPU
#   docker build -f infra/ai-train.Dockerfile --build-arg TORCH_INDEX=cu126 -t vietdoc-ai-train:cu126 .  # NVIDIA
# cu126 matches driver 560.x (CUDA 12.6); newer drivers may use a newer index.
# Training code (M1.3/M3) is not implemented yet; the default command prints the
# environment report. Weights, checkpoints and datasets are volumes, never image layers.

FROM python:3.12.15-slim-bookworm
ARG TORCH_INDEX=cpu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1
WORKDIR /app
COPY pyproject.toml ./
# Torch first from the chosen wheel index so the train extra does not pull PyPI's default build.
RUN pip install --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}" "torch==2.14.1" \
 && mkdir -p src/vietdoc && touch src/vietdoc/__init__.py \
 && pip install ".[train]" \
 && pip uninstall -y vietdoc && rm -rf src
COPY src ./src
COPY specs/contracts ./specs/contracts
RUN pip install --no-deps . && rm -rf build src/*.egg-info \
 && groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /models /datasets /artifacts/evaluation \
 && chown app:app /models /artifacts/evaluation
ENV VIETDOC_CONTRACTS_DIR=/app/specs/contracts \
    VIETDOC_MODELS_DIR=/models \
    HF_HOME=/models/.hf-cache
USER app
CMD ["python", "-m", "vietdoc.entrypoints.cli.env_report"]
