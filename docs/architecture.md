# Architecture

Halekhoob is a server-rendered Django application for a single owner. It uses
progressively enhanced templates and vanilla JavaScript; there is no frontend
build step. `tokens.css` is exposed through the `theme/tokens.css` symlink.

## Request and data flow

1. The authenticated owner submits a supported public source URL with moods and
   an optional note. Canonical source keys prevent duplicate entries.
2. Django stores the video and its durable queued status in the database.
3. A separate `runworker` process claims one item at a time, downloads with yt-dlp,
   normalizes media through FFmpeg, extracts audio and a thumbnail, and validates
   the output before marking it ready.
4. Local deployments store files under `DATA_DIR`. Server deployments upload
   validated objects to a private R2 bucket using the Standard storage class.
5. The timeline selects matching records and embeds authenticated media routes.
   Local routes support byte ranges; R2 routes redirect to temporary signed URLs.

## Main modules

| Path | Responsibility |
| --- | --- |
| `library/models.py`, `migrations/` | Archive, moods, job state and worker lease |
| `library/views.py`, `forms.py`, `urls.py` | Private pages, media and API routes |
| `library/validation.py`, `network.py` | Supported URLs and download network guards |
| `library/downloader.py`, `audio.py` | Download, media normalization and validation |
| `library/worker.py` | Local queue and recovery under a filesystem lock |
| `library/cloud_worker.py`, `leases.py` | PostgreSQL queue ownership and lease renewal |
| `library/r2.py`, `storage.py` | Object storage and local filesystem operations |
| `library/management/commands/` | Workers, archive import/export and audio preparation |
| `static/timeline.js`, `audio-player.js` | Inline video feed and continuous audio |

## Persistence and recovery

SQLite is intended for local storage. PostgreSQL is required for production R2.
Local queue processing uses a filesystem lock; cloud processing uses renewable
leases and per-job ownership tokens. A video is published only after validation.
Failures retain the source and labels, with retry state persisted in the database.

The local archive defaults to a 100 GB cap; the Docker example starts at 8 GB.
These are application limits, not provider billing controls. Worker disk headroom
is reserved for conversion. R2 deletions are delayed seven days to allow recovery;
metadata-only backups depend on the referenced objects still existing.

Portable full backups include objects and SHA-256 checksums. Restore into a new,
empty database and preferably a separate bucket prefix. Do not run a restore
against an actively processing archive.

## Deployment boundaries

The Docker stack has four services: web, worker, PostgreSQL and an independent
Nginx gateway. PostgreSQL has no published port. Web and worker have separate R2
credentials. The TLS overlay supports an independent listener without replacing
an existing host's Nginx. CI validates code; production updates are manual.

See [deployment](server-deployment.md), [testing](testing.md) and
[security](../SECURITY.md) for operational details.
