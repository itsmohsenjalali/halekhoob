#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
configuration="${SERVER_ENV_FILE:-.env.server}"
compose=(docker compose --env-file "$configuration" -f deploy/compose.server.yml)
if grep -qx 'ENABLE_TLS=1' "$configuration"; then
    compose+=(-f deploy/compose.tls.yml)
fi
exec "${compose[@]}" "$@"
