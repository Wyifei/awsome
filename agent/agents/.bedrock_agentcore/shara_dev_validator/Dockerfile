# syntax=docker/dockerfile:1
# SHARA Validator Agent
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better layer caching)
COPY validator/requirements.txt .

# Install dependencies with BuildKit cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy shared modules
COPY shared/ /app/shared/

# Copy validator code
COPY validator/ /app/validator/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080
ENV LOG_LEVEL=INFO

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

WORKDIR /app/validator

# Use opentelemetry-instrument for automatic OTEL instrumentation
CMD ["opentelemetry-instrument", "python", "-m", "uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8080"]
