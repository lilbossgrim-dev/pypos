"""Database-neutral table description derived from collection specs.

``describe`` is pure Python (testable without SQLAlchemy). ``build_table`` turns a
description into a SQLAlchemy ``Table``; the Alembic migration is generated from the
same description by ``scripts/gen_migration.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from pypos.core.store import CollectionSpec

KEY_LENGTH = 255
ID_LENGTH = 128  # composite ids such as '<warehouse>:<product>' exceed 64 chars
MERCHANT_LENGTH = 64
_MAX_IDENT = 60


@dataclass(frozen=True)
class TableDef:
    name: str
    key_columns: tuple[str, ...]  # extra String(255) columns (besides merchant_id)
    uniques: tuple[tuple[str, tuple[str, ...]], ...]  # (constraint name, columns)
    indexes: tuple[tuple[str, tuple[str, ...]], ...]  # (index name, columns)


def _ident(prefix: str, table: str, cols: tuple[str, ...]) -> str:
    raw = f"{prefix}_{table}_{'_'.join(cols)}"
    if len(raw) <= _MAX_IDENT:
        return raw
    digest = hashlib.sha1(raw.encode()).hexdigest()[:8]
    return f"{raw[: _MAX_IDENT - 9]}_{digest}"


def describe(spec: CollectionSpec[Any]) -> TableDef:
    table = f"pypos_{spec.name}"
    key_cols = tuple(f for f in spec.key_fields if f != "merchant_id")
    uniques = tuple((_ident("uq", spec.name, g), g) for g in spec.unique)
    idx: list[tuple[str, tuple[str, ...]]] = [
        (_ident("ix", spec.name, ("merchant_id",)), ("merchant_id",))
    ]
    idx += [(_ident("ix", spec.name, g), g) for g in spec.indexes if g != ("merchant_id",)]
    return TableDef(table, key_cols, uniques, tuple(idx))


def build_table(metadata: Any, spec: CollectionSpec[Any]) -> Any:
    """Create the SQLAlchemy ``Table`` for ``spec`` (requires SQLAlchemy)."""
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    d = describe(spec)
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    cols: list[Any] = [
        sa.Column("id", sa.String(ID_LENGTH), primary_key=True),
        sa.Column("merchant_id", sa.String(MERCHANT_LENGTH), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", json_type, nullable=False),
        *[sa.Column(c, sa.String(KEY_LENGTH), nullable=True) for c in d.key_columns],
    ]
    items: list[Any] = [sa.UniqueConstraint(*cols_, name=n) for n, cols_ in d.uniques]
    items += [sa.Index(n, *cols_) for n, cols_ in d.indexes]
    return sa.Table(d.name, metadata, *cols, *items)
