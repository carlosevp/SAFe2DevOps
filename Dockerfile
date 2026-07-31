# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /frontend
RUN corepack enable && corepack prepare pnpm@10.34.3 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.12-slim-bookworm AS backend-build
WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DATA_DIR=/data \
    FRONTEND_DIST=/app/frontend/dist \
    PORT=8000 \
    HOME=/tmp \
    PYTHONPATH=/app/backend

# OpenShift arbitrary UID: root group writable paths only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/backend /app/frontend/dist /data /tmp \
    && chgrp -R 0 /app /data /tmp \
    && chmod -R g+rwX /app /data /tmp \
    && chmod g+s /data

COPY --from=backend-build /usr/local /usr/local
COPY backend /app/backend
COPY --from=frontend-build /frontend/dist /app/frontend/dist
COPY scripts/container_entrypoint.sh /app/container_entrypoint.sh
COPY scripts/ops_admin.py /app/scripts/ops_admin.py
COPY config /app/config

RUN chmod 755 /app/container_entrypoint.sh \
    && chmod 755 /app/scripts/ops_admin.py \
    && chgrp -R 0 /app \
    && chmod -R g+rwX /app

USER 1001
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health/live" || exit 1

ENTRYPOINT ["/app/container_entrypoint.sh"]
