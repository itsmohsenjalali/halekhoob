# Security policy

Security fixes target the latest `main` branch. There are no supported release
branches yet.

Please report vulnerabilities through GitHub's **Security → Report a vulnerability**
on this repository. Do not post exploitable details, passwords, personal video
links, database exports or signed media URLs in public issues.

Include the affected commit, reproduction steps using synthetic data, impact and
any suggested fix. This is a personal project; response times are not guaranteed.

## Deployment boundaries

- This application is designed for one owner, not public registration or a
  multi-tenant service. Mood management is shared between accounts.
- Keep PostgreSQL private and R2 public access disabled. Use distinct bucket-scoped
  read-only web and read/write worker credentials.
- R2 URLs are temporary bearer links: anyone with a still-valid signed URL can
  access that object. Avoid sharing or logging them.
- Use HTTPS for public access. Loopback HTTP is intended for local development
  or an SSH tunnel only.
- Backups contain private account and archive data. Keep them outside Git and
  regularly test recovery into an isolated database and bucket prefix.
