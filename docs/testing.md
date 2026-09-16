# Testing

## Automated suite

Install the development requirements from an activated Python 3.12 environment.
FFmpeg/FFprobe and Node.js 22 must be available on `PATH`.

```sh
python -m pip install -r backend/requirements-dev.in
export DJANGO_DEBUG=1
export DATA_DIR="$(mktemp -d)"
(cd backend && pytest -q)
ruff check .
python backend/manage.py makemigrations --check --dry-run
(cd backend && node --test tests/audio-renewal.test.cjs)
```

The temporary `DATA_DIR` avoids creating data in the source tree. Test fixtures
isolate files and Django creates a separate test database. Tests use synthetic
FFmpeg clips and mocked R2 objects, not the personal library.

For PostgreSQL coverage, provision a disposable PostgreSQL 17 database and set
`DATABASE_URL` to its connection string before running pytest. The test role must
be able to create and drop test databases. Never point tests at production.

CI runs both database variants, lint, migrations, JavaScript audio-state tests,
and web/worker Docker builds. JavaScript media doubles test event handling; they
do not prove browser autoplay or physical-device lock-screen behavior.

## Manual acceptance

Use an isolated installation, a test account, and a separate R2 prefix when
applicable. Check:

- Public YouTube and Instagram downloads, file validation, audio and mobile seek.
- Duplicate links, download failure/retry and recovery after worker restart.
- Quota exhaustion without losing previous files.
- Anonymous access denial, private thumbnails and signed-URL expiration.
- Filtering and viewport autoplay without leaving the timeline.
- Continuous audio while changing tabs; on real phones, lock/unlock and track
  transitions. Record the browser and OS version with the result.
- Full-backup restoration into an empty database and fresh media location.

`scripts/smoke_downloads.py` accepts exactly ten distinct public URLs covering both
platforms, a new `--data-dir`, and a `--report` destination. It deliberately refuses
cloud database/storage configuration. Keep source-link lists and resulting reports
private. Platform availability varies with source permissions, IP and extractor
version; passing deterministic CI does not prove live download availability.


## Multi-user acceptance

Use two independent Google accounts. Save the same source URL in each; verify independent categories, favorites and notes. Attempt to read, edit, retry, download or inject the other account's IDs and expect 404/400. Confirm logged-out requests return 401 and expired/wrong-origin JWTs fail. Verify a fresh user starts with an empty archive and personal default categories.

Check the pre-existing owner archive after its configured verified Google account signs in. Confirm attachment downloads return the stored file and seeking works. Change filters while loading more videos; only the current filter may appear. Favorite a playing video without resetting playback. Exercise continuous audio, next/previous, expired URL renewal, hidden tabs and a real phone's lock screen.

Run frontend `npm run typecheck` and `npm run build`. Run the complete backend suite in Linux with working FFmpeg for SQLite and PostgreSQL. Migration and backup tests must use disposable databases, never production.
