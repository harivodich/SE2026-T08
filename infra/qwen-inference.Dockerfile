# syntax=docker/dockerfile:1
# Isolated AI-2 inference tooling. No model weights, OCR runtime or credentials.
FROM python:3.12.15-slim-bookworm
ARG TORCH_INDEX=cu126
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    HF_HOME=/tmp/huggingface \
    XDG_CACHE_HOME=/tmp/cache \
    TORCH_HOME=/tmp/torch \
    OMP_NUM_THREADS=2
WORKDIR /app
# Preserve existing train/contract pins; only PyYAML is additional, image-local tooling.
RUN pip install --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}" "torch==2.14.1" \
 && pip install "transformers==5.20.2" "safetensors==0.8.0" \
    "jsonschema==4.26.0" "referencing==0.37.0" "PyYAML==6.0.3" \
 && pip check
COPY src/vietdoc ./src/vietdoc
COPY specs/contracts ./specs/contracts
ENV PYTHONPATH=/app/src \
    VIETDOC_CONTRACTS_DIR=/app/specs/contracts
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app \
 && mkdir /results && chown app:app /results
USER app
ENTRYPOINT ["python", "-B", "-m", "vietdoc.ml.qwen_smoke"]
