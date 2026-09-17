#!/usr/bin/env bash
# Optionally publish only this application's certificate to a shared ingress.
# The ingress must already persist /etc/letsencrypt and contain our vhost.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -n "${INGRESS_CONTAINER:-}" ]] || exit 0
: "${INGRESS_TLS_DOMAIN:?Set INGRESS_TLS_DOMAIN}"
[[ "$INGRESS_CONTAINER" =~ ^[a-zA-Z0-9_.-]+$ ]]
[[ "$INGRESS_TLS_DOMAIN" =~ ^[a-zA-Z0-9.-]+$ ]]
umask 077
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
gateway=$(deploy/server.sh ps -q gateway)
target="/etc/letsencrypt/halekhoob/$INGRESS_TLS_DOMAIN"
for file in fullchain.pem privkey.pem; do
    docker cp -L "$gateway:/etc/letsencrypt/live/$INGRESS_TLS_DOMAIN/$file" "$staging/$file"
    chmod 600 "$staging/$file"
done
docker exec "$INGRESS_CONTAINER" mkdir -p "$target"
docker cp "$staging/." "$INGRESS_CONTAINER:$target/"
docker exec "$INGRESS_CONTAINER" nginx -t
docker exec "$INGRESS_CONTAINER" nginx -s reload
