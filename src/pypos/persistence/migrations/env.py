"""Alembic environment. The database URL comes from the Alembic config
(``sqlalchemy.url``), the ``PYPOS_DATABASE_URL`` variable, or a connection passed in
``config.attributes['connection']`` (used by ``pypos.ops.run_migrations``)."""

import os

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool

from pypos.persistence.schema import build_table
from pypos.persistence.specs import CORE_SPECS

config = context.config
target_metadata = MetaData()
for _spec in CORE_SPECS:
    build_table(target_metadata, _spec)


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("PYPOS_DATABASE_URL", "")
    if not url:
        raise RuntimeError("set sqlalchemy.url or PYPOS_DATABASE_URL")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
