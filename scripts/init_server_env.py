#!/usr/bin/env python3
"""Create a private Docker configuration without printing credentials."""

import argparse
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit


def read_env(path):
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path(".env.server"))
    parser.add_argument("--web-key", type=Path, default=Path(".env.r2-web"))
    parser.add_argument("--worker-key", type=Path, default=Path(".env.r2-worker"))
    parser.add_argument("--public-url", default="http://127.0.0.1:8088")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    if args.destination.exists():
        parser.error("Destination already exists; do not regenerate live database passwords.")
    origin = urlsplit(args.public_url)
    if origin.scheme not in {"https", "http"} or not origin.hostname:
        parser.error("Supply a valid HTTP(S) origin.")
    if origin.scheme == "http" and origin.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use HTTPS for public access, or loopback HTTP through SSH.")
    if args.port in {22, 80, 443} or not 1024 <= args.port <= 65535:
        parser.error("Choose a separate unprivileged application port.")
    web, worker = read_env(args.web_key), read_env(args.worker_key)
    shared = ["R2_ENDPOINT_URL", "R2_BUCKET_NAME", "R2_PREFIX"]
    if any(web[key] != worker[key] for key in shared):
        parser.error("Both keys must use the same R2 endpoint, bucket and prefix.")
    values = {
        "DJANGO_SECRET_KEY": secrets.token_hex(48),
        "POSTGRES_ADMIN_PASSWORD": secrets.token_hex(32),
        "POSTGRES_APP_PASSWORD": secrets.token_hex(32),
        "APP_BIND_HOST": "127.0.0.1",
        "APP_PORT": str(args.port),
        "APP_PUBLIC_URL": args.public_url.rstrip("/"),
        "PROXY_SCHEME": origin.scheme,
        "DJANGO_ALLOWED_HOSTS": f"localhost,127.0.0.1,web,{origin.hostname}",
        **{key: web[key] for key in shared},
        "R2_WEB_ACCESS_KEY_ID": web["R2_ACCESS_KEY_ID"],
        "R2_WEB_SECRET_ACCESS_KEY": web["R2_SECRET_ACCESS_KEY"],
        "R2_WORKER_ACCESS_KEY_ID": worker["R2_ACCESS_KEY_ID"],
        "R2_WORKER_SECRET_ACCESS_KEY": worker["R2_SECRET_ACCESS_KEY"],
        "R2_URL_TTL": "3600",
        "DEFAULT_USER_STORAGE_BYTES": "1000000000",
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "",
        "CLERK_SECRET_KEY": "",
        "CLERK_ISSUER": "",
        "CLERK_LEGACY_OWNER_EMAIL": "",
    }
    with os.fdopen(
        os.open(args.destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
    ) as file:
        file.write("".join(f"{key}={value}\n" for key, value in values.items()))
    print(f"Private server configuration created: {args.destination}")


if __name__ == "__main__":
    main()
