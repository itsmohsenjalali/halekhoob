#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
deploy/server.sh run --rm --no-deps certbot renew --webroot -w /var/www/certbot --quiet
deploy/server.sh exec -T gateway nginx -t
deploy/server.sh exec -T gateway nginx -s reload
