# =============================================================================
# Fraud Generator — Dockerfile
# Multi-stage: builder installs deps, runtime is slim
# Runs as non-root for security
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps for confluent-kafka (needs librdkafka)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# =============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime deps for confluent-kafka
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Non-root user
RUN useradd -r -u 1001 generator
USER generator

# Prometheus metrics
EXPOSE 9101

ENTRYPOINT ["python", "main.py"]
