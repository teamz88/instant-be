# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=3

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
# Install dependencies with retry logic and increased timeout for large packages
# Split installation to handle large packages (like CUDA) separately
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --timeout 300 --retries 3 -r requirements.txt || \
    (echo "First attempt failed, retrying with longer timeout..." && \
     pip install --no-cache-dir --timeout 600 --retries 5 --no-deps -r requirements.txt && \
     pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt)

# Copy project
COPY . .

# Copy and make entrypoint script executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/media /app/logs

# Expose port
EXPOSE 9001

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9001/api/health/ || exit 1

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:9001", "--workers", "4", "--timeout", "120", "ai_agent.wsgi:application"]