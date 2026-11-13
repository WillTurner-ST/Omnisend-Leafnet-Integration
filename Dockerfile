FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY middleware ./middleware
COPY .env.example .env.example

# Create directory for persistent sqlite db
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/middleware.db
ENV PORT=18743

EXPOSE 18743

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD sh -c 'curl -f "http://localhost:${PORT:-18743}/health" || exit 1'

CMD ["sh", "-c", "uvicorn middleware.main:app --host 0.0.0.0 --port ${PORT:-18743}"]
