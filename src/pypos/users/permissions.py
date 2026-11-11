"""Permission catalogue and built-in roles."""

from __future__ import annotations

PERMISSIONS: frozenset[str] = frozenset(
    {
        "products.read", "products.write",
        "inventory.read", "inventory.adjust", "inventory.transfer", "inventory.count",
        "sales.create", "sales.read", "sales.cancel", "sales.discount", "sales.reprint",
        "payments.read", "payments.refund",
        "cash.open", "cash.close", "cash.move", "cash.read",
        "customers.read", "customers.write",
        "suppliers.read", "suppliers.write",
        "purchasing.read", "purchasing.write", "purchasing.receive",
        "returns.create", "returns.authorize",
        "reports.read",
        "users.read", "users.manage",
        "branches.read", "branches.manage",
        "taxes.manage",
        "audit.read",
    }
)  # fmt: skip

BUILTIN_ROLES: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "manager": PERMISSIONS - {"users.manage", "taxes.manage"},
    "cashier": frozenset(
        {
            "products.read", "inventory.read", "sales.create", "sales.read", "sales.reprint",
            "cash.open", "cash.close", "cash.read", "customers.read", "customers.write", "returns.create",
        }
    ),
    "inventory_clerk": frozenset(
        {
            "products.read", "products.write", "inventory.read", "inventory.adjust",
            "inventory.transfer", "inventory.count", "purchasing.read", "purchasing.receive",
            "suppliers.read",
        }
    ),
    "viewer": frozenset(p for p in PERMISSIONS if p.endswith(".read")),
}  # fmt: skip


def is_valid_permission(value: str) -> bool:
    """Known permission, ``"*"`` or a ``prefix.*`` wildcard over a known prefix."""
    if value in PERMISSIONS or value == "*":
        return True
    if value.endswith(".*"):
        prefix = value[:-1]
        return any(p.startswith(prefix) for p in PERMISSIONS)
    return False
