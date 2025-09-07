# syntax=docker/dockerfile:1
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        gcc \
        libpq-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Create app directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv sync --no-install-project

# Development stage - fast rebuilds, no user switching
FROM base as dev
COPY . .
RUN uv sync
EXPOSE 8000 8501
CMD ["uv", "run", "python", "-c", "print('Dev container ready. Use docker-compose to run specific services.')"]

# Production stage - includes security hardening
FROM base as production
COPY . .
RUN uv sync

# Create data directory with proper permissions
RUN mkdir -p /app/data

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app \
    && chown -R app:app /app/data
USER app

EXPOSE 8000 8501
CMD ["uv", "run", "python", "-c", "print('Container ready. Use docker-compose to run specific services.')"]