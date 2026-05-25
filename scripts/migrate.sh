#!/bin/sh
set -e

echo "[migrate] Aguardando MySQL aceitar conexoes..."

MAX=30
I=0
until python - <<'PYEOF'
import os, sys
try:
    import pymysql
    pymysql.connect(
        host=os.environ.get('DB_HOST', 'db'),
        user=os.environ.get('MYSQL_USER', 'portal'),
        password=os.environ.get('MYSQL_PASSWORD', 'portalsecret'),
        database=os.environ.get('MYSQL_DATABASE', 'unifi_portal'),
        connect_timeout=3
    ).close()
except Exception as e:
    print(f'  -> {e}', file=sys.stderr)
    sys.exit(1)
PYEOF
do
    I=$((I+1))
    if [ "$I" -ge "$MAX" ]; then
        echo "[migrate] ERRO: banco nao respondeu apos $MAX tentativas."
        exit 1
    fi
    echo "[migrate] Tentativa $I/$MAX... aguardando 2s"
    sleep 2
done

echo "[migrate] Banco pronto. Executando alembic upgrade head..."
alembic upgrade head
echo "[migrate] Migrations concluidas com sucesso!"
