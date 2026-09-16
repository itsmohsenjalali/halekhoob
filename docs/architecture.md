# Architecture and API

The Next.js App Router frontend owns navigation and presentation. Nginx routes `/api/v1/` and `/healthz/` to Django and all other requests to Next.js. Clerk protects application pages; Django independently validates every API Bearer token using the configured issuer's JWKS, RS256, expiration, session/subject and exact authorized origin. Legacy Django session cookies do not authorize API requests.

Clerk must enable only Google. The API additionally checks the primary verified Google identity and banned/locked account status against Clerk, caching that lookup for at most one minute. Clerk IDs map uniquely to internal accounts. The optional legacy owner email permits a one-time association with the existing `owner`; it never merges arbitrary users by email.

Every category and video belongs to one user. Querysets and mutations enforce ownership, including submitted category IDs, status, playlist and attachment endpoints. Identical source URLs can exist in different archives. R2 objects use per-owner prefixes for new uploads; migrated objects keep their keys and gain database ownership.

## Endpoints

All paths below start with `/api/v1/` and require `Authorization: Bearer <Clerk session token>` except a valid short-lived local media ticket.

| Method | Path | Result |
| --- | --- | --- |
| GET | `me/` | Profile, stored/reserved bytes and daily/queue limits |
| GET, POST | `categories/` | List or create personal categories |
| PATCH, DELETE | `categories/{id}/` | Rename/update or remove a category; preserve videos |
| GET, POST | `videos/` | Paginated archive or enqueue a source URL |
| GET, PATCH, DELETE | `videos/{id}/` | Own video metadata, edit, or delete |
| POST | `videos/{id}/retry/` | Retry a failed source download within quotas |
| GET | `videos/{id}/download/?kind=video` | Expiring attachment URL (`audio` also supported) |
| GET | `playlist/` | Matching ready audio tracks |
| GET, HEAD | `media/?ticket=...` | Local development media using a signed expiring ticket |

List and playlist accept `category`, `q`, and `filter=favorites`; list also supports `filter=pending` and `page`. Create accepts `source_url`, `category_ids`, optional `title` and `note`. Duplicate creation returns the existing own record. Errors are JSON with `error.code` and a Persian `error.message`.

## Queue and storage

Admission locks the archive and account, reserves conversion space, checks global/per-user storage and queue caps, and increments daily usage atomically. A single worker uses durable PostgreSQL leases and job tokens. It chooses the least recently served active account, then the next eligible job. Failed uploads remain in the object journal for cleanup; finished and failed jobs release reservations, automatic retries retain them.

The worker validates media before marking a video ready. R2 uploads explicitly use Standard storage and private object keys. Playback and downloads use expiring signed URLs; attachment responses carry Content-Disposition. These URLs are temporary bearer credentials, valid until expiry even after logout. Deletion is deferred to preserve backup recoverability and counts toward quotas until objects are removed.

The Next.js timeline chooses the most visible card for autoplay and pauses video when hidden or an audio queue starts. A persistent audio element advances tracks and supports Media Session actions. It renews expired media links through the authenticated API. Background playback is subject to browser/OS policy.

## Backups and migration

Portable exports include users, account mappings, daily usage, personal categories, videos and object metadata. Full exports also contain media. The importer accepts older single-owner exports and assigns category/object ownership. Restore into an empty migrated database with workers stopped. Existing Clerk subject mappings require the same Clerk instance on restore; another instance needs a deliberate identity migration.

Migration 0005 assigns legacy global categories to their users, adds accounts and object ownership, and changes source deduplication to per-user uniqueness. It is not automatically reversible; restore a pre-upgrade backup to roll back.
