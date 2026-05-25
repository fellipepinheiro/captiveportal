import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

# Importa os models para que o metadata seja populado
from app.extensions import db
from app.models import *  # noqa: F401,F403

config = context.config

# Le a URL do banco da variavel de ambiente em runtime
# Isso garante que o Docker injete a variavel corretamente
db_url = os.environ.get('DATABASE_URL') or config.get_main_option('sqlalchemy.url')
config.set_main_option('sqlalchemy.url', db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.metadata


def run_migrations_offline():
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
