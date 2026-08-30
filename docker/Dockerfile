# Stage 1: build the runner
FROM node:24-alpine AS runner
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
COPY schema/ ../schema/
RUN npm run build

# Stage 2: backend + built runner served by WhiteNoise.
# The Python minor and the uv version are the ones CI tests with
# (.github/workflows/ci.yml); bump both together.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv
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
# collectstatic only needs settings to import; the build-time key is never persisted.
RUN SECRET_KEY=build-only-not-persisted python manage.py collectstatic --noinput
# The app never writes to the image: run it as an unprivileged user that owns
# nothing under /app (the build output is world-readable). It does get a home:
# gunicorn keeps its control socket under $HOME and logs an error without one.
RUN useradd --system --create-home --shell /usr/sbin/nologin app
USER app
EXPOSE 8000
# load_definitions exits non-zero when a file is skipped (reported above it) or
# when it cannot run at all (unreadable /data mount, database gone); either way
# the app starts with the definitions already in the database, so one bad file
# does not keep the whole deployment down. The exit code is printed as is.
CMD ["sh", "-c", "python manage.py migrate --noinput && { python manage.py load_definitions || echo \"load_definitions exited $? (see above); starting with the definitions already in the database\" >&2; } && exec gunicorn prolog.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3}"]
