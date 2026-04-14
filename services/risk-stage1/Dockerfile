# =============================================================================
# Stage 1 Fast Risk Service — Dockerfile
# Multi-stage: builder installs heavy deps, runtime is slim
# =============================================================================

FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ librdkafka-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka1 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . .
RUN useradd -r -u 1003 stage1svc && \
    mkdir -p /tmp/matplotlib && \
    touch model/__init__.py routes/__init__.py
ENV HOME=/tmp
ENV MPLCONFIGDIR=/tmp/matplotlib
USER stage1svc
EXPOSE 8100 9103
ENTRYPOINT ["python", "main.py"]
