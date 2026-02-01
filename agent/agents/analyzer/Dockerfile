# syntax=docker/dockerfile:1
# SHARA Analyzer Agent

# ============== Builder Stage ==============
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy requirements first (for better layer caching)
COPY analyzer/requirements.txt .

# Install dependencies with BuildKit cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r requirements.txt

# ============== Runtime Stage ==============
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install system dependencies and apply security updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy shared modules
COPY shared/ /app/shared/

# Copy analyzer code
COPY analyzer/ /app/analyzer/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080
ENV LOG_LEVEL=DEBUG

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

WORKDIR /app/analyzer

# Use opentelemetry-instrument for automatic OTEL instrumentation
CMD ["opentelemetry-instrument", "python", "-m", "uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8080"]
