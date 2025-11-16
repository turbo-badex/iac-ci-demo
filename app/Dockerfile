FROM python:3.11-slim

# Create non-root user (good practice)
RUN useradd -m appuser

WORKDIR /app

# Install system deps (psycopg2 needs these) & clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Change ownership
RUN chown -R appuser:appuser /app
USER appuser

ENV PORT=8080

# Expose port
EXPOSE 8080

# Use gunicorn for production-style server
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]