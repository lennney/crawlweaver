FROM python:3.12-slim

LABEL maintainer="CrawlWeaver"
LABEL description="CrawlWeaver — 12-Factor content extraction + SEO generation"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY *.py ./
COPY tools/ tools/
COPY web/ web/
COPY prompts/ prompts/
COPY cache/ cache/

# Data directories (mounted as volumes)
RUN mkdir -p /data/output /data/review /data/state /data/publish

# Environment
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')"

# Default: run web server
CMD ["python", "cli.py", "serve", "--host", "0.0.0.0", "--port", "8080"]
