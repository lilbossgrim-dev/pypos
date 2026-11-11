"""Every core collection, in dependency-neutral order (also drives the DB schema)."""

from __future__ import annotations

from typing import Any

from pypos.audit import AUDIT_LOG
from pypos.branches import BRANCHES, TERMINALS, WAREHOUSES
from pypos.cash_management import CASH_MOVEMENTS, CASH_SESSIONS
from pypos.core.counters import COUNTERS
from pypos.core.idempotency import IDEMPOTENCY
from pypos.core.store import CollectionSpec
from pypos.customers import CUSTOMERS
from pypos.inventory import STOCK_COUNTS, STOCK_LEVELS, STOCK_MOVEMENTS
from pypos.payments import PAYMENTS, REFUNDS
from pypos.products import BARCODES, CATEGORIES, PRODUCTS, UNITS
from pypos.purchasing import PURCHASE_ORDERS
from pypos.returns import RETURNS
from pypos.sales import SALES
from pypos.suppliers import SUPPLIERS
from pypos.taxation import TAX_RULES
from pypos.users import ROLES, USERS

CORE_SPECS: tuple[CollectionSpec[Any], ...] = (
    TAX_RULES, USERS, ROLES, BRANCHES, WAREHOUSES, TERMINALS, UNITS, CATEGORIES, PRODUCTS,
    BARCODES, STOCK_LEVELS, STOCK_MOVEMENTS, STOCK_COUNTS, CUSTOMERS, SUPPLIERS,
    PURCHASE_ORDERS, SALES, PAYMENTS, REFUNDS, CASH_SESSIONS, CASH_MOVEMENTS, RETURNS,
    AUDIT_LOG, IDEMPOTENCY, COUNTERS,
)  # fmt: skip
