# ==============================================================================
# Production Dockerfile for FastAPI Standalone Budget App
# Fully optimized for Cloud Hosts (Render, Railway, Fly.io, etc.) & Local Docker
# ==============================================================================

FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Set working directory
WORKDIR /app

# Install minimal system dependencies (curl for container health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create a non-root system user for security compliance and assign permissions
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose container port (documentation purpose; Render dynamically routes traffic)
EXPOSE 8000

# Health check to ensure application is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/login || exit 1

# Launch uvicorn bound to dynamic $PORT injected by cloud provider (fallback: 8000)
# 'exec' ensures uvicorn runs as PID 1 to receive OS signals (SIGTERM/SIGINT) cleanly
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
