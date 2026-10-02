# Dockerfile
# Production-ready container for Moroccan CNIE OCR Microservice & KYC Dashboard

FROM python:3.10-slim-bookworm

# 1. Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

# 2. Minimal system dependencies (headless mode: no heavy X11/OpenGL/LLVM packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3. Working directory
WORKDIR /app

# 4. Install pre-compiled wheels (fast, lightweight, no source compilation)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# 5. Copy application source code and web assets
COPY src/ /app/src/
COPY static/ /app/static/
COPY data/ /app/data/

# 7. Create persistent runtime directories
RUN mkdir -p /app/data/extracted_faces /app/reports

# 8. Expose microservice port
EXPOSE 8000

# 9. Healthcheck against FastAPI endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 10. Launch Uvicorn server
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
