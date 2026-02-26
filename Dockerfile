FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for compiled packages (solders, Levenshtein)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Production image ---
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY bot/ bot/
COPY config/ config/
COPY database/ database/
COPY data/ data/
COPY analysis/ analysis/
COPY monitoring/ monitoring/
COPY smart_money/ smart_money/
COPY utils/ utils/

# Don't copy .env, venv, .git, tests, etc.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Database will be stored in /app/db (mounted volume)
RUN mkdir -p /app/db

# Run as non-root user
RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app
USER botuser

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "-m", "bot.main"]
