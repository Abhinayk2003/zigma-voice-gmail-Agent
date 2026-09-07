from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from app.config.settings import get_settings
from app.database.base import Base
from app.database import models


# =========================================================
# Alembic Config
# =========================================================

config = context.config


# =========================================================
# Logging
# =========================================================

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# =========================================================
# Application Settings
# =========================================================

settings = get_settings()


# =========================================================
# SQLAlchemy Metadata
# =========================================================

# Importing models above registers all SQLAlchemy models
# with Base.metadata.

target_metadata = Base.metadata


# =========================================================
# Database URL
# =========================================================

database_url = settings.database_url

if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not configured."
    )


# =========================================================
# Offline Migration
# =========================================================

def run_migrations_offline() -> None:
    """
    Run migrations without creating a database connection.
    """

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# =========================================================
# Online Migration
# =========================================================

def run_migrations_online() -> None:
    """
    Run migrations using a live database connection.
    """

    configuration = config.get_section(
        config.config_ini_section
    )

    configuration["sqlalchemy.url"] = database_url

    connectable = engine_from_config(
        configuration,
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


# =========================================================
# Run
# =========================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
