FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wa_digest ./wa_digest

# Mount a Railway volume here so episodes and the bookmark survive redeploys
ENV DATA_DIR=/data
# Railway sets $PORT; default for local docker runs
CMD ["sh", "-c", "uvicorn wa_digest.web:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
