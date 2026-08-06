# Multi-stage so the runtime image carries no build toolchain.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Never run the API as root: a compromised worker with root in the
# container is a much shorter path to the rest of the cluster.
RUN groupadd --system hpf && useradd --system --gid hpf --home /app hpf
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=hpf:hpf . /app

RUN mkdir -p /app/var/uploads /app/var/models && chown -R hpf:hpf /app/var
USER hpf

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

# Worker count is set per-deployment; pandas aggregations are CPU-bound and
# oversubscribing cores makes p99 latency worse, not better.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
