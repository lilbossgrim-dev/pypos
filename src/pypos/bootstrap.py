"""Wiring helpers: pick the storage backend and seed mandatory reference data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pypos.config import POSConfig
from pypos.core.events import EventBus
from pypos.core.store import MemoryStore, Store

if TYPE_CHECKING:
    from pypos.application import POS


def build_store(config: POSConfig, bus: EventBus) -> Store:
    if config.database_url.startswith("memory://"):
        return MemoryStore(bus)
    from pypos.persistence.sql import SQLStore

    return SQLStore(config.database_url, echo=config.db_echo, bus=bus)


def seed_defaults(app: POS, merchant_id: str | None = None) -> None:
    """Create built-in roles and measurement units for a merchant (idempotent)."""
    merchant = merchant_id or app.config.merchant_id
    with app.store.transaction() as tx:
        app.users.ensure_builtin_roles(tx, merchant)
        app.products.ensure_default_units(tx, merchant)
