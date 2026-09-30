# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

ARG LAYA_VERSION=0.3.20
ARG TORCH_VERSION=2.14.0
ARG TORCH_INDEX=cpu

# The `serve` extra provides `laya-serve`, which exposes POST /v1/systemone.
# Model weights are deliberately not downloaded during build: they live in the
# persistent Hugging Face cache mounted at /data/huggingface. Runtime settings,
# including HF_TOKEN, are supplied by Compose from the untracked .env file.
RUN pip install --disable-pip-version-check --no-cache-dir "torch==${TORCH_VERSION}" --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}" \
    && pip install --disable-pip-version-check --no-cache-dir "laya[serve]==${LAYA_VERSION}" \
    && pip check \
    && groupadd --system laya \
    && useradd --system --gid laya --create-home laya \
    && mkdir -p /data/huggingface \
    && chown -R laya:laya /data

COPY --chown=laya:laya ticket_triage_poc.py /app/ticket_triage_poc.py

USER laya
WORKDIR /home/laya

EXPOSE 8000

# This allows `docker run` users to persist the cache too. Compose maps this
# location to the named `laya-model-cache` volume.
VOLUME ["/data/huggingface"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10m --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["laya-serve"]
