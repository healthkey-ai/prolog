# Developer/CI entry points (mirrors .github/workflows/ci.yml). Requires uv, node, PostgreSQL.
.PHONY: lint test test-backend test-backend-integrated test-frontend e2e build check

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run python manage.py makemigrations --check --dry-run
	cd frontend && npm run -s typecheck

test: test-backend test-backend-integrated test-frontend

test-backend:
	cd backend && uv run pytest -q

test-backend-integrated:
	cd backend && POSTGRES_DB=prolog_integrated PROLOG_PROFILE=integrated PROLOG_PARTICIPANT_MODEL=auth.User uv run pytest -q --no-migrations

test-frontend:
	cd frontend && npm test -s

e2e:
	cd frontend && npx playwright test

build:
	cd frontend && npm run -s build

check: lint test build e2e
