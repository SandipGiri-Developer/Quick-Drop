FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies


# Copy application code
COPY . .

# Install production dependencies, plus testing dependencies so tests can be run inside docker via `docker compose exec`
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir pytest pytest-cov hypothesis httpx ruff mypy

# Create a non-root user and change ownership
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck to verify the FastAPI server is running
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start command
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port 8000"]
