#!/usr/bin/env bash
# Run only on a fresh Ubuntu 24.04 Always Free VM, AFTER mounting the data volume.
set -euo pipefail
umask 022
if [[ $EUID -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
SITE_HOST=${1:?Usage: sudo bash deploy/bootstrap.sh archive.PUBLIC_IP.sslip.io}
if [[ ! "$SITE_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+$ ]]; then echo 'Invalid hostname.' >&2; exit 1; fi
if ! mountpoint -q /srv/motivation; then echo 'Mount the persistent data volume at /srv/motivation first.' >&2; exit 1; fi
SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
apt-get update
apt-get install -y python3.12 python3.12-venv ffmpeg nginx certbot python3-certbot-nginx curl xz-utils rsync
id motivation >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/motivation --shell /usr/sbin/nologin motivation
install -d -m 0755 /opt/motivation/app /etc/motivation
install -d -m 0700 -o motivation -g motivation /srv/motivation/data
if [[ "$SOURCE_DIR" != /opt/motivation/app ]]; then
  rsync -a --exclude=.venv --exclude=.git --exclude=data --exclude=artifacts --exclude=staticfiles --exclude=.env --exclude=__pycache__ "$SOURCE_DIR/" /opt/motivation/app/
fi
chmod 0755 /opt/motivation/app/deploy/manage.sh
python3.12 -m venv /opt/motivation/venv
/opt/motivation/venv/bin/pip install --no-cache-dir -r /opt/motivation/app/requirements-worker.txt
# Official Node distribution, verified against its published SHA256 list.
NODE_VERSION=v22.23.2
case "$(uname -m)" in aarch64) NODE_ARCH=arm64;; x86_64) NODE_ARCH=x64;; *) exit 1;; esac
if [[ ! -x /opt/motivation/node/bin/node ]]; then
  NODE_TEMP=$(mktemp -d)
  NODE_ARCHIVE="node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
  curl --fail --location --output "$NODE_TEMP/$NODE_ARCHIVE" "https://nodejs.org/dist/$NODE_VERSION/$NODE_ARCHIVE"
  curl --fail --location --output "$NODE_TEMP/SHASUMS256.txt" "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt"
  (cd "$NODE_TEMP" && grep " $NODE_ARCHIVE\$" SHASUMS256.txt | sha256sum -c -)
  install -d /opt/motivation/node
  tar -xJf "$NODE_TEMP/$NODE_ARCHIVE" --strip-components=1 -C /opt/motivation/node
  rm -rf -- "$NODE_TEMP"
fi
if [[ ! -f /etc/motivation/app.env ]]; then
  /opt/motivation/venv/bin/python - "$SITE_HOST" <<'PY'
import secrets,sys
from pathlib import Path
host=sys.argv[1]
text=Path('/opt/motivation/app/deploy/app.env.example').read_text()
text=text.replace('REPLACE_WITH_A_RANDOM_SECRET',secrets.token_urlsafe(64)).replace('archive.YOUR_PUBLIC_IP.sslip.io',host)
path=Path('/etc/motivation/app.env')
path.write_text(text)
path.chmod(0o640)
PY
fi
chown root:motivation /etc/motivation/app.env
set -a
source /etc/motivation/app.env
set +a
cd /opt/motivation/app
runuser -u motivation --preserve-environment -- /opt/motivation/venv/bin/python manage.py migrate --noinput
/opt/motivation/venv/bin/python manage.py collectstatic --noinput
/opt/motivation/venv/bin/python manage.py check --deploy --fail-level WARNING
install -m 0644 deploy/motivation-web.service deploy/motivation-worker.service /etc/systemd/system/
cat > /etc/nginx/sites-available/motivation <<NGINX
server {
    listen 80;
    server_name $SITE_HOST;
    client_max_body_size 1m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_buffering off;
        proxy_read_timeout 120s;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/motivation /etc/nginx/sites-enabled/motivation
nginx -t
systemctl daemon-reload
systemctl enable --now motivation-web motivation-worker
systemctl reload nginx
certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect -d "$SITE_HOST"
echo 'Create your private account (the password prompt stays on this server):'
runuser -u motivation --preserve-environment -- /opt/motivation/venv/bin/python manage.py createsuperuser
echo "Site configured: https://$SITE_HOST — configure backups before adding your archive."
