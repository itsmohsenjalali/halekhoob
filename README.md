# Halekhoob · حال‌خوب

A self-hosted, private video library organized by how you want to feel.
Save public YouTube and Instagram video links, tag them with moods, and revisit
local copies in a Persian, right-to-left timeline.

[راهنمای فارسی](README.fa.md) · [Server deployment](docs/server-deployment.md) ·
[Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md)

## Features

- Inline, mobile-friendly timeline with mood filters, search and favorites.
- Viewport autoplay with in-video playback and sound controls.
- Continuous audio playlist for the current selection, with media-session controls.
- Durable background downloads, duplicate detection, progress and retry handling.
- Private playback and seeking; local files or signed Cloudflare R2 URLs.
- Portable backups with checksums, restore commands and scheduled server backups.
- Self-hosted fonts and no analytics or AI processing.

## Stack

Python 3.12 · Django 5.2 · vanilla JavaScript · yt-dlp · FFmpeg · Node.js 22.
Use SQLite and local media for development, or Docker with PostgreSQL 17 and a
private **Cloudflare R2 Standard** bucket for a server deployment. The web app
and downloader are separate processes; downloads require a persistent worker.

## Quick start

Install Python 3.12, FFmpeg (including `ffprobe`) and Node.js 22, then:

```sh
git clone https://github.com/itsmohsenjalali/halekhoob.git
cd halekhoob
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-worker.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

In another terminal in the same directory:

```sh
. .venv/bin/activate
export DJANGO_DEBUG=1
python manage.py runworker
```

Open **http://127.0.0.1:8000**. There is no public registration. Create only one
owner account. Local data is stored in the ignored `data/` directory. The app
reads process environment variables; it does **not** automatically load `.env`.
Allow at least 3.5 GB of free working space with the default download settings.
Use [Docker deployment](docs/server-deployment.md) for public access.

## Repository layout

```text
config/       Django settings and entry points
library/      Models, views, downloads, storage, migrations and commands
templates/    Persian RTL pages and timeline fragments
static/       JavaScript, CSS and licensed fonts
theme/        Shared design-token asset
tests/        Python and JavaScript tests
scripts/      Backup, configuration and manual acceptance tools
deploy/       Docker, Nginx, environment examples and systemd services
docs/         Architecture, testing and deployment guides
.github/      CI and contribution templates
```

Secrets, personal media, databases and deployment reports are not part of the
repository. Copy the configuration examples and provide your own credentials.

## Server installation

Follow [the Docker + PostgreSQL + R2 guide](docs/server-deployment.md). The Compose
stack contains a web app, worker, private database and gateway. It can run beside
an existing website using a separate port. A legacy bare-metal Oracle guide is
available in [docs/deployment.md](docs/deployment.md); its infrastructure quotas
must be checked before use.

## Limits and playback behavior

- Intended for a **single owner**, not a multi-tenant public service.
- Public, single videos only: up to 20 minutes, 500 MB and 720p. No cookies,
  private content, livestreams, playlists or multi-item posts.
- Public sources can still reject downloads or require login from a server IP.
  Failed downloads retain their link and tags for retry.
- Video autoplay starts muted and pauses outside the viewport or in a hidden tab.
  Continuous audio mode keeps playing across tab changes. Lock-screen playback
  and automatic advancement depend on the browser and operating system; closing
  the tab ends the playlist. Real-device lock-screen support is not guaranteed.
- Local playback requires authentication. R2 redirects use expiring signed links;
  anyone holding an unexpired link can access that object.
- Only download media you have permission to retain. The MIT code license does
  not license third-party videos. No sample archive or account is included.
- R2, compute, backups and traffic may incur provider charges. The application's
  storage cap is configurable; it is not a cloud billing limit.

## Development and testing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [the test guide](docs/testing.md).
CI runs Python tests with SQLite and PostgreSQL, JavaScript audio tests, lint,
migration checks and both Docker builds. Real-platform downloads are tested
separately without production credentials.

## License and security

[MIT](LICENSE), with [separate font notices](THIRD_PARTY_NOTICES.md).
Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
