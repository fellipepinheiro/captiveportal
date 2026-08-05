"""Campos do visitante deixam de ser obrigatorios no banco

O modelo sempre declarou full_name, cpf, email e mobile como opcionais, mas
a migration inicial criou as quatro colunas NOT NULL e nenhuma migration
posterior corrigiu. Enquanto o portal exigia CPF e telefone de todo mundo o
descompasso nao aparecia; com os campos configuraveis pelo administrador,
qualquer instalacao que nao peca CPF passa a falhar no cadastro — o insert
manda NULL para uma coluna que nao aceita, e o visitante recebe um erro
generico sobre dado duplicado.

So aparece em instalacao nova: bancos criados antes ja estao permissivos, o
que escondeu o problema durante todo o desenvolvimento.

O tipo atual de cada coluna e lido do proprio banco em vez de ser fixado
aqui. Instalacoes diferentes chegaram a esta altura por caminhos diferentes
(tamanhos de VARCHAR divergem entre elas), e reescrever o tipo com um valor
chutado poderia truncar dado existente.

Revision ID: 20260805_0010
Revises: 20260804_0009
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = '20260805_0010'
down_revision = '20260804_0009'
branch_labels = None
depends_on = None

COLUNAS = ('full_name', 'cpf', 'email', 'mobile')


def _tipos_atuais() -> dict:
    inspector = sa.inspect(op.get_bind())
    return {c['name']: c for c in inspector.get_columns('visitors')}


def upgrade():
    atuais = _tipos_atuais()
    for nome in COLUNAS:
        col = atuais.get(nome)
        if col is None or col.get('nullable'):
            continue  # ja opcional (ou inexistente) — nada a fazer
        op.alter_column('visitors', nome,
                        existing_type=col['type'],
                        nullable=True)


def downgrade():
    # Nao volta: as linhas gravadas depois desta migration podem ter NULL
    # nessas colunas, e restaurar o NOT NULL falharia. O estado anterior
    # tambem era o errado — o modelo nunca exigiu esses campos.
    pass
