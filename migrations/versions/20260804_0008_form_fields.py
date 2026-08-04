"""campos do formulario configuraveis pelo admin

Revision ID: 20260804_0008
Revises: 20260803_0007
Create Date: 2026-08-04
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = '20260804_0008'
down_revision = '20260803_0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'form_fields',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('key', sa.String(40), nullable=False),
        sa.Column('stage', sa.String(10), nullable=False),
        sa.Column('label', sa.String(80), nullable=False),
        sa.Column('field_type', sa.String(20), nullable=False, server_default='text'),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('required', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('is_key', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('placeholder', sa.String(120), nullable=True),
        sa.Column('help_text', sa.String(200), nullable=True),
        sa.Column('options', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('key', 'stage', name='uq_form_fields_key_stage'),
    )
    op.create_index('ix_form_fields_stage', 'form_fields', ['stage'])

    # Campos livres nao tem coluna propria; ficam aqui para que acrescentar
    # uma pergunta nova nao exija migration.
    with op.batch_alter_table('visitors') as batch_op:
        batch_op.add_column(sa.Column('extra_data', sa.Text, nullable=True))

    # Semeia exatamente o formulario que existe hoje, para que a instalacao
    # continue funcionando igual enquanto ninguem mexer na configuracao.
    agora = datetime.now(timezone.utc)
    tabela = sa.table(
        'form_fields',
        sa.column('key', sa.String), sa.column('stage', sa.String),
        sa.column('label', sa.String), sa.column('field_type', sa.String),
        sa.column('enabled', sa.Boolean), sa.column('required', sa.Boolean),
        sa.column('is_key', sa.Boolean), sa.column('order', sa.Integer),
        sa.column('placeholder', sa.String), sa.column('help_text', sa.String),
        sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime),
    )
    def campo(key, stage, label, tipo, req, chave, ordem, ph=None, ajuda=None):
        return {'key': key, 'stage': stage, 'label': label, 'field_type': tipo,
                'enabled': True, 'required': req, 'is_key': chave, 'order': ordem,
                'placeholder': ph, 'help_text': ajuda,
                'created_at': agora, 'updated_at': agora}

    op.bulk_insert(tabela, [
        campo('cpf',    'login',  'CPF',              'cpf',   True,  True,  10, '000.000.000-00'),
        campo('mobile', 'login',  'Celular / WhatsApp','phone', True,  False, 20, '(47) 99999-9999'),
        campo('full_name', 'signup', 'Nome completo', 'name',  True,  False, 10, 'Seu nome completo'),
        campo('email',  'signup', 'E-mail',           'email', False, False, 20, 'voce@exemplo.com',
              'Opcional'),
    ])


def downgrade():
    with op.batch_alter_table('visitors') as batch_op:
        batch_op.drop_column('extra_data')
    op.drop_index('ix_form_fields_stage', table_name='form_fields')
    op.drop_table('form_fields')
