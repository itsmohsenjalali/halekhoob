# Docker server deployment with PostgreSQL and R2

This guide installs Halekhoob in `/opt/halekhoob`. Substitute your own host, domain,
R2 account and credentials. It contains no configuration for a particular live
installation. Use a Linux server with Docker Engine and the Compose plugin;
allow at least 4 GB RAM and sufficient disk for downloads, builds and backups.

## 1. Obtain the code

On the server:

```sh
git clone https://github.com/itsmohsenjalali/halekhoob.git /opt/halekhoob
cd /opt/halekhoob
install -m 600 deploy/server.env.example .env.server
```

The public repository can be fetched without a GitHub token or deploy key. Keep
`.env.server` private and outside Git. Never regenerate passwords on an existing
database. Docker reads this file through `deploy/server.sh`.

## 2. Configure the bucket and application

Create a private **Cloudflare R2 Standard** bucket with public access disabled.
Create two S3-compatible credentials scoped to that bucket: read-only for web,
read/write for the worker. Enter them in `.env.server` along with:

- `R2_ENDPOINT_URL`: the account's HTTPS S3 API endpoint.
- `R2_BUCKET_NAME`, `R2_PREFIX`: the bucket and a dedicated prefix such as `archive`.
- `DJANGO_SECRET_KEY`: a long random secret.
- `POSTGRES_ADMIN_PASSWORD` and `POSTGRES_APP_PASSWORD`: different random hex
  passwords. Hex avoids URL-encoding issues in the database connection string.
- `DEFAULT_USER_STORAGE_BYTES`: storage quota for newly created accounts (1 GB by default). Existing quotas are managed in `/admin`.

Generate each secret separately with `python3 -c 'import secrets; print(secrets.token_hex(48))'`
in your own private terminal. Do not commit output or reuse credentials.
Alternatively, `scripts/init_server_env.py` can combine existing private web and
worker R2 environment files; run it with `--help` for supported arguments.

In the R2 dashboard, configure bucket CORS using `deploy/r2-cors.json`, replacing
`https://archive.example.com:8443` with your actual application origin, including
its port. CORS does not make the bucket public. Web playback redirects to expiring
signed URLs; do not share them. Never apply the example origin unchanged.

### Clerk Google-only login

Configure a Clerk application for your domain. Enable Google and disable email, phone, username, password, passkeys, biometric and wallet sign-in/signup. Production Google OAuth credentials and Clerk DNS records must be configured in the provider dashboards.

Set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, private `CLERK_SECRET_KEY` and `CLERK_ISSUER` in `.env.server`. `APP_PUBLIC_URL` must exactly match the origin including its port; Compose uses it as the backend authorized party. The public key is embedded when building Next.js, so rebuild the frontend after changing it. The secret is runtime-only and must never have a `NEXT_PUBLIC_` prefix.

Use standard HTTPS port **443** for the public production origin. Allowlisting a nonstandard port can make existing-user sign-in work while new-user CAPTCHA validation still fails. Clerk's Account Portal can also discard redirect destinations with a nonstandard port. Test a genuinely new Google account as well as an existing account before releasing. See [Clerk's production origin requirements](https://clerk.com/docs/guides/development/troubleshooting/using-production-keys-in-development#run-your-server-with-https-on-port-443).

Set `APP_PUBLIC_URL` to the canonical origin (for example `https://archive.example.com`). The frontend redirects alternate hosts/ports there before authentication. The backend independently checks the same exact origin; update R2 CORS when changing it.

On an upgrade, set `CLERK_LEGACY_OWNER_EMAIL` to the verified Google email that owns the old `owner` archive. After its first successful sign-in, the archive remains bound to that Clerk subject. New installations leave this empty. New accounts receive `DEFAULT_USER_STORAGE_BYTES`. Staff can edit each existing account’s storage quota at `/admin`. There are no duration, per-file 500 MB, daily-count or queue-count caps.

## 3. Start through an SSH tunnel

The default configuration binds the gateway to `127.0.0.1:8088`. PostgreSQL has no
public port; only the application containers join its private network.

```sh
COMPOSE_PARALLEL_LIMIT=1 deploy/server.sh build web worker frontend
deploy/server.sh up -d db
deploy/server.sh run --rm web python manage.py migrate --noinput
deploy/server.sh up -d web worker frontend
deploy/server.sh up -d --no-deps --force-recreate gateway
deploy/server.sh ps
curl --fail http://127.0.0.1:8088/healthz/
```

From your computer, forward the loopback port:

```sh
ssh -N -L 8088:127.0.0.1:8088 USER@YOUR_SERVER
```

Then open `http://127.0.0.1:8088` with Clerk development keys, or use the configured HTTPS origin with production keys. Google sign-in provisions each account.
Do not publish loopback HTTP to the internet. Public origins require HTTPS.

## 4. HTTPS behind an existing site's ingress

Keep the application gateway on 8443 and add a separate domain vhost to the
existing ingress on 443. `deploy/nginx/shared-ingress.conf.example` shows the
routing, including TLS verification of the upstream gateway. Substitute the
domain and the host gateway address reachable from the ingress container.
Do not replace the existing site's server blocks. Preserve the original ingress
configuration, run `nginx -t`, then reload it without restarting its containers.
Persist the new vhost in the ingress's mounted configuration so recreation keeps it.

The optional `deploy/sync-ingress-tls.sh` copies **only Halekhoob's certificate**
into `/etc/letsencrypt/halekhoob/DOMAIN` in the ingress container, validates Nginx,
and reloads it. The ingress must persist that directory. Configure
`INGRESS_CONTAINER` and `INGRESS_TLS_DOMAIN` in a systemd override for
`halekhoob-tls-renew.service`; the renewal script invokes this helper after
renewing the application's own certificate. For initial setup, sync the
certificate before enabling the new vhost. Never mount the other site's
certificate volume into Halekhoob or alter its certificates.

### Independent gateway TLS setup

The supplied TLS overlay listens on port 8443, so the existing ingress continues
using ports 80 and 443. This listener is an upstream for production authentication,
not the canonical user-facing address. To use the Let's Encrypt webroot flow:

1. Point your domain's DNS to this server and allow inbound TCP 8443.
2. Arrange for your existing HTTP server on port 80 to serve
   `/.well-known/acme-challenge/` for this domain from a Docker volume. This must
   work before requesting a certificate. The overlay does not configure the
   existing site's Nginx for you.
3. In `.env.server`, set `ENABLE_TLS=1`, `TLS_DOMAIN=archive.example.com`,
   `TLS_PORT=8443`, `TLS_BIND_HOST=0.0.0.0`, `APP_PUBLIC_URL=https://archive.example.com`,
   `PROXY_SCHEME=https`, and add the domain to `DJANGO_ALLOWED_HOSTS`.
   Set `ACME_WEBROOT_VOLUME` to that existing webroot volume's exact name.
4. Obtain a certificate before recreating the gateway:

```sh
deploy/server.sh run --rm --no-deps certbot certonly --non-interactive \
  --agree-tos --email YOUR_EMAIL --webroot -w /var/www/certbot -d YOUR_DOMAIN
deploy/server.sh up -d web worker frontend
deploy/server.sh up -d --no-deps --force-recreate gateway
curl --fail https://archive.example.com:8443/healthz/
deploy/server.sh run --rm --no-deps certbot renew --dry-run --no-random-sleep-on-renew
```

The certificate is held in the application's own `halekhoob_tls-data` volume.
Only the ACME webroot is shared with the application containers. The renewal
script reloads this application's gateway and, when configured, syncs its
certificate to the shared ingress. Verify both the public origin and the
existing site's HTTPS response after configuring ingress and renewal.

## 5. Day-to-day commands

```sh
cd /opt/halekhoob
deploy/server.sh ps
deploy/server.sh logs --tail=100 web worker frontend gateway
deploy/server.sh restart worker
deploy/server.sh logs --tail=50 frontend
```

Keep separate bucket-scoped web and worker keys. The PostgreSQL application role
has no superuser or role-creation privileges. Container memory, CPU and logs are
bounded. Download scratch space lives in `halekhoob_worker-data`; the database
lives in `halekhoob_postgres-data`.

## 6. Updating from GitHub

CI tests changes; it does not deploy them. On the server, review the incoming
changes and take a full backup before updating. Keep the previous commit ID for
rollback:

```sh
cd /opt/halekhoob
git status --short
git fetch origin
git log --oneline HEAD..origin/main
git rev-parse HEAD
python3 scripts/cloud_backup.py /var/backups/halekhoob --server --full
git pull --ff-only
COMPOSE_PARALLEL_LIMIT=1 deploy/server.sh build web worker frontend
deploy/server.sh stop worker
deploy/server.sh run --rm web python manage.py migrate --noinput
deploy/server.sh up -d web worker frontend
deploy/server.sh up -d --no-deps --force-recreate gateway
deploy/server.sh ps
```

Verify `/healthz/`, login, media playback and the queue through the configured
origin. If a step fails after stopping the worker, resolve the failure and
explicitly start it again. A rollback of source/images does not reverse database
migrations: review migration compatibility and restore a tested backup if needed.
Do not use `docker compose down -v` for an update; it deletes database volumes.

## 7. Backups and TLS renewal

From `/opt/halekhoob`, install the supplied service/timer files after confirming
their schedule and backup path:

```sh
install -m 644 deploy/halekhoob-backup.service deploy/halekhoob-backup.timer /etc/systemd/system/
install -m 644 deploy/halekhoob-full-backup.service deploy/halekhoob-full-backup.timer /etc/systemd/system/
# Only when the TLS overlay is configured:
install -m 644 deploy/halekhoob-tls-renew.service deploy/halekhoob-tls-renew.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now halekhoob-backup.timer halekhoob-full-backup.timer
# Only when the TLS overlay is configured:
systemctl enable --now halekhoob-tls-renew.timer
systemctl list-timers --all 'halekhoob-*'
```

The defaults retain four daily metadata backups and four weekly full backups in
`/var/backups/halekhoob`. Schedules use the server timezone. Full export needs
roughly twice the archive's size in scratch space in addition to retained
backups. Fetch a private copy to another machine regularly; these timers alone
do not provide off-server protection.

```sh
python3 scripts/cloud_backup.py /var/backups/halekhoob --server --full
journalctl -u halekhoob-backup.service -n 50 --no-pager
```

Backups contain private account and archive data. Restore to an empty database,
preferably with a fresh bucket prefix, after `migrate` and before creating an
owner. Use `import_portable` with write-capable R2 credentials; inspect its `--help`
for arguments. Stop the worker and make the input readable by container UID 10001.
Metadata-only restore requires the original objects to remain available; full
backups include the objects. R2 deletion is delayed seven days by default.

Run the [manual acceptance checks](testing.md#manual-acceptance) on your own server
before relying on it for an archive.

### Administration and host monitoring

After the intended administrator signs in through Clerk, explicitly grant access:

```sh
deploy/server.sh exec -T web python manage.py set_archive_admin owner@example.com
```

Only the selected, already-linked user receives Django `is_staff`; registration never grants it automatically. `/admin` uses the same Google sign-in as the archive. The API checks staff access on every request. User quotas are integer bytes, accept zero to stop new downloads, and never delete existing files when reduced. Changes are recorded with actor, target, previous/new value and timestamp. Retained R2 deletion objects still count until cleanup (normally seven days).

Install the optional host collector before starting the new web container:

```sh
install -d -m 755 /var/lib/halekhoob-monitor
install -m 644 deploy/halekhoob-monitor.service deploy/halekhoob-monitor.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now halekhoob-monitor.timer
systemctl start halekhoob-monitor.service
```

The collector assumes this documented `/opt/halekhoob` installation and Docker data on `/var/lib/docker`. It writes coarse host CPU/RAM/disk/uptime and status of this app’s five containers every 30 seconds. The web container mounts **only this snapshot directory, read-only**; it receives no Docker socket or host process filesystem. Missing or older-than-90-second samples are flagged in the UI. Database latency and worker lease are checked live. Monitoring is a current snapshot, not historical graphs or an alerting service.

The single worker determines its byte budget from current account usage at execution time, bounds download/transcode output, and checks quota again at publication (including a quota reduction during upload). Queue admission no longer reserves a fixed 525 MB per unknown-length video. Disk reserve, finite subprocess timeouts, public-source validation and 720p conversion remain operational safeguards. `ARCHIVE_MAX_BYTES` is retained only for the disabled legacy interface; it does not cap multi-user downloads.


### YouTube requests human verification

A public video may fail from the server with `Sign in to confirm you’re not a bot`. The worker reports `source_verification`, preserves the link/categories/note, and does not automatically repeat this challenge. Signing into Halekhoob through Google does not authenticate the separate YouTube downloader.

Check the worker's installed yt-dlp version and its Node/EJS dependencies first. If a direct, cookie-free extraction inside the worker returns this verification response as well, the source is refusing the server request before media download; changing quotas, duration limits or R2 will not fix it. Do not silently copy user browser cookies or send their links through unconfigured third-party download services. A source-authorized download route must be configured and tested separately; successful playback in a user's browser does not prove that server downloads are available.

References: [yt-dlp YouTube notes](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube), [JavaScript runtime requirements](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
