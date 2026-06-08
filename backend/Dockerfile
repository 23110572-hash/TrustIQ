# TrustIQ backend image
FROM python:3.11-slim

# System deps for psycopg2 and scientific wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source and trained ML artefacts.
COPY backend /app/backend
COPY ml /app/ml

WORKDIR /app/backend

EXPOSE 8000

# uvicorn entry point.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
