#!/bin/sh
# Picks the HTTP-only or HTTPS config, links the right certificate and reloads Nginx
# every 6 hours so renewed Let's Encrypt certificates are picked up automatically.
set -e
DOMAIN="${DOMAIN:-localhost}"
CERTS=/etc/nginx/certs
LE="/etc/letsencrypt/live/${DOMAIN}"
rm -f /etc/nginx/conf.d/*.conf

link_certs() {
  mkdir -p "$CERTS"
  if [ -f "$LE/fullchain.pem" ]; then
    ln -sf "$LE/fullchain.pem" "$CERTS/fullchain.pem"
    ln -sf "$LE/privkey.pem" "$CERTS/privkey.pem"
  elif [ ! -e "$CERTS/fullchain.pem" ]; then
    # Temporary self-signed certificate so Nginx can start before Let's Encrypt has run.
    echo "No Let's Encrypt certificate yet for ${DOMAIN}; using a temporary self-signed one."
    openssl req -x509 -nodes -newkey rsa:2048 -days 7 -subj "/CN=${DOMAIN}" \
      -keyout "$CERTS/privkey.pem" -out "$CERTS/fullchain.pem" >/dev/null 2>&1
  fi
}

if [ "$DOMAIN" = "localhost" ]; then
  cp /etc/nginx/pdfdesk/http.conf.template /etc/nginx/conf.d/pdfdesk.conf
else
  link_certs
  envsubst '${DOMAIN}' < /etc/nginx/pdfdesk/https.conf.template > /etc/nginx/conf.d/pdfdesk.conf
  (
    while :; do
      sleep 6h
      link_certs
      nginx -s reload
    done
  ) &
fi

exec nginx -g 'daemon off;'
