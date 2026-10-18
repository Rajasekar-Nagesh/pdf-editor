#!/usr/bin/env bash
# Requests the first Let's Encrypt certificate for $DOMAIN and reloads Nginx.
# Run once after "docker compose up -d", when your domain already points to this server.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

if [ "${DOMAIN:-localhost}" = "localhost" ]; then
  echo "DOMAIN is 'localhost' in .env - set your real domain first." >&2
  exit 1
fi

echo "Requesting a certificate for ${DOMAIN} ..."
docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${LETSENCRYPT_EMAIL}" \
  --agree-tos --no-eff-email --non-interactive

# Point Nginx at the new certificate and reload it.
docker compose exec nginx sh -c "ln -sf /etc/letsencrypt/live/${DOMAIN}/fullchain.pem /etc/nginx/certs/fullchain.pem && ln -sf /etc/letsencrypt/live/${DOMAIN}/privkey.pem /etc/nginx/certs/privkey.pem && nginx -s reload"
echo "Done. Open https://${DOMAIN}"
