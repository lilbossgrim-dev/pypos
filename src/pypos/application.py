"""The :class:`POS` application object: composition root of the framework."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pypos import __version__
from pypos.audit import AuditService
from pypos.bootstrap import build_store, seed_defaults
from pypos.branches import BranchService
from pypos.cash_management import CashService
from pypos.config import POSConfig
from pypos.core.context import OperationContext
from pypos.core.events import EventBus, Handler
from pypos.core.store import CollectionSpec, Store
from pypos.customers import CustomerService
from pypos.inventory import InventoryService
from pypos.payments import PaymentService
from pypos.persistence.specs import CORE_SPECS
from pypos.plugins import Plugin, PluginManager
from pypos.products import ProductService
from pypos.purchasing import PurchasingService
from pypos.reporting import ReportService
from pypos.returns import ReturnService
from pypos.sales import SalesService
from pypos.suppliers import SupplierService
from pypos.taxation import TaxService
from pypos.users import UserService


class POS:
    """Entry point::

        pos = POS(POSConfig(database_url="sqlite:///store.db", currency="MXN"))
        pos.initialize()
        pos.products, pos.inventory, pos.sales, ...

    All business rules live in the services; the CLI and HTTP API call the same ones.
    """

    def __init__(
        self,
        config: POSConfig | None = None,
        *,
        plugins: list[Plugin] | None = None,
        plugin_config: dict[str, dict[str, Any]] | None = None,
        store: Store | None = None,
    ) -> None:
        self.config = config or POSConfig()
        self.store: Store = store or build_store(
            self.config, EventBus(raise_errors=self.config.event_errors_raise)
        )
        self.bus: EventBus = self.store.bus
        self.extensions: dict[str, Any] = {}
        self.plugin_collections: list[CollectionSpec[Any]] = []
        self.plugin_commands: dict[str, Callable[..., Any]] = {}
        self.plugin_routes: list[Callable[[POS], Any]] = []
        self.plugin_migrations: list[Path] = []
        self._initialized = False

        for spec in CORE_SPECS:
            self.store.register(spec)

        self.audit = AuditService(self)
        self.taxes = TaxService(self)
        self.users = UserService(self)
        self.branches = BranchService(self)
        self.products = ProductService(self)
        self.inventory = InventoryService(self)
        self.customers = CustomerService(self)
        self.suppliers = SupplierService(self)
        self.purchasing = PurchasingService(self)
        self.payments = PaymentService(self)
        self.cash = CashService(self)
        self.sales = SalesService(self)
        self.returns = ReturnService(self)
        self.reporting = ReportService(self)

        self.plugin_manager = PluginManager(__version__)
        self.plugin_manager.load(self, list(plugins or []), dict(plugin_config or {}))

    # ---- lifecycle ----------------------------------------------------
    def initialize(self) -> POS:
        """Create the schema (if ``auto_create_schema``) and seed roles/units. Idempotent."""
        if self.config.auto_create_schema:
            self.store.initialize()
        seed_defaults(self)
        for name in self.plugin_manager.order:
            self.plugin_manager.plugins[name].on_initialize(self)
        self._initialized = True
        return self

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> POS:
        return self.initialize()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- helpers ------------------------------------------------------
    def tx(self) -> Any:
        """Open a (re-entrant) transaction: ``with pos.tx() as tx: ...``."""
        return self.store.transaction()

    def subscribe(self, event: str, handler: Handler) -> None:
        self.bus.subscribe(event, handler)

    def system_context(
        self, branch_id: str | None = None, terminal_id: str | None = None
    ) -> OperationContext:
        """Unrestricted context for trusted code (setup scripts, CLI, tests)."""
        return OperationContext.system(self.config.merchant_id).with_location(
            branch_id, terminal_id
        )

    def context_for(
        self, user_id: str, *, branch_id: str | None = None, terminal_id: str | None = None
    ) -> OperationContext:
        return self.users.context_for(user_id, branch_id=branch_id, terminal_id=terminal_id)

    def health(self) -> dict[str, Any]:
        db_ok, detail = True, "ok"
        try:
            ping = getattr(self.store, "ping", None)
            if ping is not None:
                ping()
            else:
                with self.store.transaction():
                    pass
        except Exception as exc:
            db_ok, detail = False, f"{type(exc).__name__}: {exc}"
        return {"status": "ok" if db_ok else "degraded", "version": __version__,
                "database": {"ok": db_ok, "detail": detail},
                "initialized": self._initialized}  # fmt: skip

    def modules(self) -> list[dict[str, str]]:
        core = [
            "audit",
            "taxes",
            "users",
            "branches",
            "products",
            "inventory",
            "customers",
            "suppliers",
            "purchasing",
            "payments",
            "cash",
            "sales",
            "returns",
            "reporting",
        ]
        rows = [{"name": n, "kind": "core", "version": __version__} for n in core]
        rows += [{"name": n, "kind": "plugin", "version": self.plugin_manager.plugins[n].version}
                 for n in self.plugin_manager.order]  # fmt: skip
        return rows

    def __getattr__(self, name: str) -> Any:
        ext = self.__dict__.get("extensions", {})
        if name in ext:
            return ext[name]
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")
