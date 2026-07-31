from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.types import TypeDecorator

from core.db_setup import DATABASE_URL
from models.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """EncryptedString ist ein TypeDecorator über TEXT — in der DB steht schlicht
    TEXT. Ohne diesen Vergleich auf dem darunterliegenden Typ meldet jedes
    `--autogenerate` einen Typwechsel TEXT→EncryptedString und erzeugt eine
    ALTER-Migration, die nichts ändert. Das verrauscht genau die Prüfung, mit der
    man ein echtes Schema-Delta finden will.

    None = Alembics Standardvergleich übernimmt.
    """
    if isinstance(metadata_type, TypeDecorator):
        return metadata_type.impl_instance._compare_type_affinity(inspected_type) is False
    return None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        compare_type=compare_type,
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
            compare_type=compare_type,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
