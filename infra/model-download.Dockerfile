# syntax=docker/dockerfile:1
# Tooling only. No weights, host credentials or model downloads at image build.
FROM python:3.12.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    HF_HOME=/tmp/huggingface
# Pin CLI dependencies too: newer typer-slim resolved without Click in the build probe.
RUN pip install "huggingface_hub==1.2.1" "typer-slim==0.20.0" "click==8.1.8" \
 && pip check \
 && hf --help > /dev/null \
 && groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app \
 && mkdir /provision && chown app:app /provision
WORKDIR /app
COPY src/vietdoc/__init__.py /app/src/vietdoc/__init__.py
COPY src/vietdoc/ml/__init__.py src/vietdoc/ml/release_manifest.py src/vietdoc/ml/model_provision.py /app/src/vietdoc/ml/
ENV PYTHONPATH=/app/src
USER app
ENTRYPOINT ["python", "-m", "vietdoc.ml.model_provision"]
