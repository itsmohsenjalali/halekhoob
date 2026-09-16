#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# A trusted, shell-compatible file with quoted values; never commit this file.
set -a
source "${CLOUD_ENV_FILE:-.env.cloud}"
set +a
# Explicit direct connection for migrations and maintenance, not the web pooler.
export DATABASE_URL="${DATABASE_DIRECT_URL:?Set DATABASE_DIRECT_URL in the private env file}"
exec .venv/bin/python backend/manage.py "$@"
