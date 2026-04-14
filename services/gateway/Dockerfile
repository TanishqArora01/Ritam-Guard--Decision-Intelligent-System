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
COPY main.py .
RUN useradd -r -u 1007 gatewaySvc
USER gatewaySvc
EXPOSE 8000 9106
ENTRYPOINT ["python", "main.py"]
