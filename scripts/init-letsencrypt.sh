#!/bin/bash
set -e

DOMAIN="portal.seudominio.com"
EMAIL="seu@email.com"

echo ">>> Subindo Nginx para validacao HTTP-01..."
docker compose up -d nginx

echo ">>> Aguardando Nginx ficar pronto..."
sleep 5

echo ">>> Emitindo certificado (dry-run primeiro)..."
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --dry-run \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN"

echo ""
read -rp "Dry-run OK. Emitir certificado real? [s/N] " confirm
if [[ "$confirm" =~ ^[sS]$ ]]; then
  docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

  echo ""
  echo ">>> Certificado emitido com sucesso!"
  echo ">>> Agora descomente o bloco HTTPS em nginx/conf.d/portal.conf"
  echo ">>> e execute: docker compose restart nginx"
else
  echo "Abortado."
fi
