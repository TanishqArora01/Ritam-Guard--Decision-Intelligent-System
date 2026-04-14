FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ librdkafka-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka1 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . .
RUN useradd -r -u 1004 stage2svc && \
    touch ensemble/__init__.py graph/__init__.py anomaly/__init__.py routes/__init__.py
USER stage2svc
EXPOSE 8200 9104
ENTRYPOINT ["python", "main.py"]
