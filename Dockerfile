# ---- Build stage ----
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system deps needed for compiling Python packages (e.g., Pillow, psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libjpeg-dev \
        zlib1g-dev \
        libpq-dev \
        && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only requirements first (to leverage Docker layer caching)
COPY requirements.txt requirements.dev.txt ./

# Install dependencies conditionally
ARG DEV=false
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements.dev.txt; \
    fi

# ---- Runtime stage ----
FROM python:3.12-slim

LABEL maintainer="ttek.com"
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
EXPOSE 8000

# Install runtime system dependencies and WeasyPrint dependencies
# No Node.js needed - Tailwind CSS is pre-built locally
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        libpq5 \
        postgresql-client \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        libcairo2 \
        libgirepository-1.0-1 \
        gir1.2-pango-1.0 \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Add non-root user
RUN adduser --disabled-password --no-create-home app_user

# Create dirs and set ownership
RUN mkdir -p /vol/web/{media,static} /app/staticfiles && \
    chown -R app_user:app_user /vol /app/staticfiles

# Copy virtual environment from builder
COPY --from=builder --chown=app_user:app_user /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy app code (after dependencies, to maximize cache reuse)
COPY --chown=app_user:app_user . /app

# Make scripts executable
RUN chmod +x /app/docker-entrypoint.sh 2>/dev/null || true

USER app_user

# Default command - will be overridden by docker-compose
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
