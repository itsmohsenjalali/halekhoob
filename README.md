# حال‌خوب · Halekhoob

A self-hosted Persian video archive organized by how you want to feel. Each user signs in with Google and keeps their own videos, categories, notes and favorites.

## Features

- Separate **Next.js / React / TypeScript frontend** and **Django JSON API**.
- **Clerk Google-only authentication** with server-side JWT validation and independent user archives.
- Responsive RTL timeline: visible videos autoplay muted, with inline pause and sound controls.
- Filter by category, search, favorite, edit and delete without leaving the timeline.
- Continuous audio playlist with Media Session controls and expiring-link renewal. Background and lock-screen playback depend on the browser and OS; an initial user gesture can be required.
- Download the archived video or audio to your device using a short-lived attachment URL.
- Durable PostgreSQL download queue, retries, per-user quotas and fair scheduling.
- Private **Cloudflare R2 Standard** media storage; separate read-only web and read/write worker credentials.
- Docker deployment beside an existing website, plus portable backup and restore tools.

## Architecture

```text
Browser → Nginx → Next.js + Clerk
               → Django API → PostgreSQL
Browser → signed private R2 URL
Download worker → yt-dlp / FFmpeg → R2 Standard
```

```text
frontend/     Next.js application, Persian UI and media players
backend/      Django API, models, migrations, worker and backend tests
scripts/      Backup, restore verification and isolated download smoke checks
deploy/       Dockerfiles, Compose, Nginx and operational examples
docs/         Architecture, API, deployment and testing guides
```

The old Django templates remain available only with both `DJANGO_DEBUG=1` and `LEGACY_UI_ENABLED=1` for development regression testing. Production serves the Next.js UI and accepts Clerk credentials for the API.

## Run locally

Use Python 3.12, Node.js 22 and FFmpeg. Create a Clerk **development** instance with Google enabled and all other sign-in/sign-up methods disabled. Production Clerk keys are domain-bound; do not use them for localhost development.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-dev.in
export DJANGO_DEBUG=1
export DATA_DIR=/tmp/halekhoob-development
export CLERK_ISSUER=https://YOUR-DEVELOPMENT-INSTANCE.clerk.accounts.dev
export CLERK_SECRET_KEY=YOUR_PRIVATE_DEVELOPMENT_KEY
export CLERK_AUTHORIZED_PARTIES=http://localhost:3000
python backend/manage.py migrate
python backend/manage.py runserver 127.0.0.1:8000
```

In another terminal with the same backend environment, run `python backend/manage.py runworker`. Then configure and start the frontend:

```sh
cd frontend
cp .env.example .env.local
# Fill the Clerk development publishable and secret keys in .env.local.
npm ci
npm run dev
```

Open `http://localhost:3000` and sign in with Google. Accounts and six personal categories are created on first authenticated API use. No Django password or superuser is needed. Never commit private environment files, archives or credentials.

## Server deployment

Follow [the Docker server guide](docs/server-deployment.md). The stack contains Next.js, Django, a worker, PostgreSQL and its own Nginx gateway. The optional HTTPS listener uses port 8443 so a different site can retain ports 80/443. PostgreSQL and R2 stay private.

For an existing installation, take a full backup before migration. Set `CLERK_LEGACY_OWNER_EMAIL` privately to the verified Google email that owns the old `owner` archive. Its first authenticated request claims that archive once; other users receive empty archives. Existing media keys remain valid.

## Limits

- Public individual YouTube/Instagram videos only: up to 720p, bounded by each user’s remaining storage quota, with no duration, daily-count or queue-count cap. No source-account cookies, private content, livestreams or playlists.
- Defaults: 1 GB per new user, five source download attempts per UTC day and five queued jobs. Reservations include conversion headroom; existing migrated users retain an 8 GB limit. Configure defaults before signup; existing account limits are stored in the database.
- Global archive cap also applies. Deleted R2 objects count against storage until deletion completes (normally within seconds; failures are retried).
- Platform availability varies by source, server IP and extractor support. Download only media you are entitled to save.
- Self-hosting and third-party providers have their own costs and quotas; this repository does not guarantee free hosting.

See [architecture and API](docs/architecture.md), [testing](docs/testing.md), [contributing](CONTRIBUTING.md) and [security](SECURITY.md).

## License

[MIT](LICENSE). Bundled fonts retain their accompanying SIL Open Font Licenses.
