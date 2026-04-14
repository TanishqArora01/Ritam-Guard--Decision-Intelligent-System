# =============================================================================
# Feature Engineering Service — Dockerfile
# Multi-stage build, non-root, librdkafka native
# =============================================================================

FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc librdkafka-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka1 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . .
RUN useradd -r -u 1002 featureengine && \
    touch features/__init__.py store/__init__.py flink/__init__.py
USER featureengine
EXPOSE 9102
ENTRYPOINT ["python", "main.py"]
