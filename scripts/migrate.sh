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

echo "[migrate] Banco pronto. Verificando consistencia do alembic_version..."

# Detecta se a revisao gravada no banco existe nos arquivos de migration.
# Se nao existir (hash fantasma), limpa a tabela para que o alembic
# consiga reconstruir o estado a partir do zero.
python - <<'PYEOF'
import os, sys, subprocess
try:
    import pymysql
    conn = pymysql.connect(
        host=os.environ.get('DB_HOST', 'db'),
        user=os.environ.get('MYSQL_USER', 'portal'),
        password=os.environ.get('MYSQL_PASSWORD', 'portalsecret'),
        database=os.environ.get('MYSQL_DATABASE', 'unifi_portal'),
    )
    cur = conn.cursor()

    # Le a revisao atual gravada no banco
    cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("[migrate] alembic_version vazia, nenhuma correcao necessaria.")
        sys.exit(0)

    db_rev = row[0]

    # Confere se a revisao gravada existe nos arquivos de migration.
    # A verificacao e feita lendo os proprios arquivos, e nao com
    # `alembic show`: aquele comando falha por varios motivos (configuracao,
    # diretorio de trabalho, imagem desatualizada) e o retorno diferente de
    # zero nao significa que a revisao seja invalida.
    import re
    from pathlib import Path

    revisoes = set()
    for arquivo in Path("migrations/versions").glob("*.py"):
        m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", arquivo.read_text(), re.M)
        if m:
            revisoes.add(m.group(1))

    if db_rev in revisoes:
        print(f"[migrate] Revisao '{db_rev}' valida. Nenhuma correcao necessaria.")
    else:
        # Apagar alembic_version faria o upgrade tentar recriar tudo do zero
        # sobre um banco que ja tem as tabelas — o resultado e a migration
        # abortar em "table already exists", e nao um banco reconstruido.
        # Para com erro claro em vez de mexer no controle de versao sozinho.
        print(f"[migrate] ERRO: o banco esta na revisao '{db_rev}', que nao existe "
              "nos arquivos de migration desta imagem.", file=sys.stderr)
        print("[migrate] Isso costuma significar imagem desatualizada — reconstrua "
              "com 'docker compose build' antes de subir.", file=sys.stderr)
        print("[migrate] Se a revisao foi mesmo removida do projeto, ajuste com "
              "'flask db stamp <revisao>' apos conferir o schema.", file=sys.stderr)
        sys.exit(1)

    cur.close()
    conn.close()
except Exception as e:
    print(f"[migrate] ERRO na verificacao de consistencia: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "[migrate] Executando alembic upgrade head..."
alembic upgrade head
echo "[migrate] Migrations concluidas com sucesso!"
