#!/usr/bin/env bash
set -euo pipefail
# Run on YOUR COMPUTER. Downloads the snapshot through SSH; no public backup URL.
REMOTE=${1:?Usage: bash deploy/export-weekly.sh user@server /path/to/local/backups}
DESTINATION=${2:?Choose a private backup directory outside the project}
if [[ ! "$REMOTE" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.:-]+$ ]]; then echo 'Invalid SSH destination.' >&2; exit 1; fi
umask 077
mkdir -p "$DESTINATION"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
NAME="archive-$STAMP.tar"
PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Stream through SSH: no second media copy is needed on the 150 GB server disk.
if ssh "$REMOTE" "sudo /opt/motivation/app/deploy/manage.sh export_archive -" > "$DESTINATION/$NAME.partial"; then
  python3 "$PROJECT_DIR/scripts/verify_export.py" "$DESTINATION/$NAME.partial"
  mv "$DESTINATION/$NAME.partial" "$DESTINATION/$NAME"
  echo "Verified and saved $DESTINATION/$NAME."
else
  echo 'Export transfer failed; only the incomplete local .partial file was kept.' >&2
  exit 1
fi
