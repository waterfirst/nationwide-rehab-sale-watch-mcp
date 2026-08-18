FROM node:22-alpine AS web-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    REHAB_WATCH_DB_PATH=/data/rehab_watch.db \
    REHAB_WATCH_HOST=0.0.0.0 \
    REHAB_WATCH_PORT=8010

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY nationwide_rehab_sale_watch_mcp/ ./nationwide_rehab_sale_watch_mcp/
COPY server.py run_web.py manifest.json ./
COPY --from=web-builder /build/web/dist ./web/dist

RUN mkdir -p /data && chown -R app:app /app /data
USER app

EXPOSE 8010
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/health', timeout=3)"

CMD ["python", "run_web.py"]
