# Contributing

Issues and pull requests in Persian or English are welcome. Discuss substantial
features in an issue before implementing them. Include the problem, expected
behavior and a small example without private archive data.

## Development

Follow the [quick start](README.md#quick-start), then install development tools:

```sh
python -m pip install -r backend/requirements-dev.in
export DJANGO_DEBUG=1
export DATA_DIR="$(mktemp -d)"
(cd backend && pytest -q)
ruff check .
python backend/manage.py makemigrations --check --dry-run
(cd backend && node --test tests/audio-renewal.test.cjs)
```

Use Python 3.12, FFmpeg/FFprobe and Node.js 22. Keep test data separate from your
personal archive. The test suite uses generated media and mocked object storage;
it does not need production credentials. CI also runs against PostgreSQL 17.
Real-platform acceptance tests are a separate, manual step; see
[testing](docs/testing.md).

## Pull requests

- Branch from `main` and keep each change focused.
- Explain the observed problem, changed behavior and relevant validation.
- Include migrations when models change. Test both local storage and R2 behavior
  when modifying media or queue code.
- Keep the Persian RTL interface usable on mobile and desktop. Prefer plain
  Django templates and JavaScript unless a new dependency has a clear benefit.
- Never include `.env*`, credentials, databases, media, backups, signed R2 URLs or
  private deployment reports. Use example domains and synthetic fixtures.

Changes to locked dependencies should update their corresponding `.in` files and
be tested with Python 3.12. Do not enable unattended production deployment from
pull requests. Contributions are submitted under the project's MIT license;
preserve third-party notices.

Frontend checks: `cd frontend && npm ci && npm run typecheck && npm run build`. Use a Clerk development publishable key for local builds and development secrets only in ignored environment files.
