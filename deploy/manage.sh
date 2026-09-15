#!/usr/bin/env bash
set -euo pipefail
# Root reads the environment, then drops privileges before invoking Django.
set -a
source /etc/motivation/app.env
set +a
cd /opt/motivation/app
exec runuser -u motivation --preserve-environment -- /opt/motivation/venv/bin/python manage.py "$@"
