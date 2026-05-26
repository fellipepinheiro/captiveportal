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

    # Verifica se essa revisao existe nos arquivos de migration
    result = subprocess.run(
        ["alembic", "show", db_rev],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[migrate] AVISO: revisao '{db_rev}' nao encontrada nos arquivos "
              "de migration (hash fantasma).")
        print("[migrate] Limpando alembic_version para reconstrucao...")
        cur.execute("DELETE FROM alembic_version")
        conn.commit()
        print("[migrate] alembic_version limpa. O upgrade ira recriar o estado.")
    else:
        print(f"[migrate] Revisao '{db_rev}' valida. Nenhuma correcao necessaria.")

    cur.close()
    conn.close()
except Exception as e:
    print(f"[migrate] ERRO na verificacao de consistencia: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "[migrate] Executando alembic upgrade head..."
alembic upgrade head
echo "[migrate] Migrations concluidas com sucesso!"
