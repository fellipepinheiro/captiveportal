import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Adiciona raiz do projeto ao path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Configuracao do alembic.ini
config = context.config

# Resolve o alembic.ini sempre a partir da raiz do projeto,
# independente de onde o alembic é chamado.
if config.config_file_name is not None:
    ini_path = config.config_file_name
    # Se o caminho nao existe como está, tenta na raiz do projeto
    if not os.path.isabs(ini_path) and not os.path.exists(ini_path):
        ini_path = os.path.join(PROJECT_ROOT, os.path.basename(ini_path))
    if os.path.exists(ini_path):
        fileConfig(ini_path)

# Sobrescreve a URL com DATABASE_URL do ambiente
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Importa modelos para autogeneracao de migrations
from app.extensions import db
from app.models.visitor import Visitor
from app.models.portal_session import PortalSession
from app.models.consent_record import ConsentRecord
from app.models.admin_user import AdminUser

target_metadata = db.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
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
