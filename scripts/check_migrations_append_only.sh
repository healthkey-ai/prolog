#!/usr/bin/env sh
# Migrations are append-only once a release exists: a migration file present at
# the latest release tag (v*) must never be modified or deleted, because every
# database that already applied it would silently drift from the models.
# Before the first tag they may still be rewritten (recreate pre-release
# databases); the guard then only reports that it is dormant.
set -eu
cd "$(dirname "$0")/.."
tag=$(git describe --tags --abbrev=0 --match 'v*' 2>/dev/null || true)
if [ -z "$tag" ]; then
  echo "migrations: no release tag yet, append-only guard dormant (recreate pre-release databases when they change)"
  exit 0
fi
changed=$(git diff --no-renames --name-status "$tag" -- 'backend/*/migrations/*.py' | grep -E '^[MD]' || true)
if [ -n "$changed" ]; then
  echo "migrations released in $tag were modified or removed; add a new migration instead:" >&2
  echo "$changed" >&2
  exit 1
fi
echo "migrations: append-only since $tag, ok"
