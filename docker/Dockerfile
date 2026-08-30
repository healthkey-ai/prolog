# Stage 1: build the runner
FROM node:24-alpine AS runner
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
COPY schema/ ../schema/
RUN npm run build

# Stage 2: backend + built runner served by WhiteNoise
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend/ ./backend/
COPY schema/ ./schema/
COPY themes/ ./themes/
COPY --from=runner /app/frontend/dist ./frontend/dist
ENV PATH="/app/backend/.venv/bin:$PATH" DEBUG=false PROLOG_PROFILE=standalone \
    PROLOG_THEME_DIRS=/app/themes:/data/themes PROLOG_DEFINITION_DIRS=/data/surveys
WORKDIR /app/backend
RUN python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn prolog.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3}"]
