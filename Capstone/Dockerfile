# Production Dockerfile for RealEstate Hub AI Agent
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt-get/lists/*

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY . .

# Expose FastAPI application port
EXPOSE 8001

# Health check instructions
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Production server startup command
CMD ["python", "-m", "uvicorn", "app_day6:app", "--host", "0.0.0.0", "--port", "8001"]
