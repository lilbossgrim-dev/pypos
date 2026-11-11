"""Operational helpers shared by the CLI (and usable from scripts).

They contain the real logic; ``cli.py`` only parses arguments and prints.
"""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypos import __version__
from pypos.application import POS
from pypos.config import POSConfig
from pypos.exceptions import ConfigurationError, ValidationError
from pypos.plugins import discover_entry_points
from pypos.users import User

REQUIRED = ("pydantic", "SQLAlchemy", "alembic", "packaging")
OPTIONAL = {"fastapi": "api", "uvicorn": "api", "typer": "cli", "psycopg": "postgres"}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def load_config(**overrides: Any) -> POSConfig:
    """Config from ``PYPOS_*`` environment variables (raises ConfigurationError if invalid)."""
    return POSConfig.from_env(**overrides)


def validate_config(config: POSConfig) -> list[str]:
    """Return human-readable problems/warnings (empty list = nothing to report)."""
    problems: list[str] = []
    if config.secret_key is None:
        problems.append("secret_key is not set: tokens (HTTP API login) cannot be issued")
    elif len(config.secret_key.get_secret_value()) < 32:
        problems.append("secret_key must have at least 32 characters")
    if config.database_url.startswith("memory://"):
        problems.append("database_url is memory://: data is lost when the process exits")
    elif config.database_url.startswith("sqlite") and config.database_url != "sqlite://":
        problems.append("sqlite is meant for development; use PostgreSQL in production")
    return problems


def build_pos(config: POSConfig | None = None, *, with_entry_points: bool = True) -> POS:
    """Create (but do not initialise) a POS with plugins from the ``pypos.plugins`` entry points."""
    cfg = config or load_config()
    return POS(cfg, plugins=discover_entry_points() if with_entry_points else [])


def system_status(pos: POS) -> dict[str, Any]:
    h = pos.health()
    h["modules"] = pos.modules()
    h["currency"] = pos.config.currency
    h["database_url"] = pos.config.redacted()["database_url"]
    h["payment_methods"] = pos.payments.methods
    return h


def create_admin(pos: POS, username: str, password: str) -> User:
    """Create the first administrator. Refuses to run if an admin already exists."""
    pos.initialize()
    from pypos.users import USERS

    with pos.store.transaction() as tx:
        existing = [
            u for u in tx.of(USERS).find(merchant_id=pos.config.merchant_id) if "admin" in u.roles
        ]
    if existing:
        raise ValidationError(
            "an administrator already exists; use the application to add more users"
        )
    return pos.users.create_admin(username, password)


def run_migrations(
    config: POSConfig, revision: str = "head", extra_locations: list[Path] | None = None
) -> str:
    """Apply Alembic migrations to ``config.database_url`` (needs SQLAlchemy + Alembic)."""
    if config.database_url.startswith("memory://"):
        raise ConfigurationError("memory:// has no schema to migrate; set database_url")
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise ConfigurationError("Alembic is not installed: pip install pypos-framework") from exc
    import pypos.persistence as persistence_pkg

    script_dir = Path(persistence_pkg.__file__).resolve().parent / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(script_dir))
    cfg.set_main_option("sqlalchemy.url", config.database_url.replace("%", "%%"))
    if extra_locations:
        cfg.set_main_option("version_locations", " ".join([str(script_dir / "versions"),
                                                           *map(str, extra_locations)]))  # fmt: skip
    command.upgrade(cfg, revision)
    return revision


def doctor(config: POSConfig | None = None) -> list[Check]:
    """Diagnose the installation: Python, dependencies, configuration, database."""
    checks = [Check("python", sys.version_info >= (3, 11),
                    f"{platform.python_version()} ({platform.python_implementation()}); needs >= 3.11")]  # fmt: skip
    checks.append(Check("pypos", True, __version__))
    for dist in REQUIRED:
        checks.append(_dist_check(dist, required=True, extra=None))
    for dist, extra in OPTIONAL.items():
        checks.append(_dist_check(dist, required=False, extra=extra))
    try:
        cfg = config or load_config()
        checks.append(Check("config", True, "valid"))
        for problem in validate_config(cfg):
            checks.append(Check("config-warning", True, problem, required=False))
        pos = build_pos(cfg, with_entry_points=False)
        health = pos.health()
        checks.append(Check("database", health["database"]["ok"], health["database"]["detail"]))
    except Exception as exc:
        checks.append(Check("config", False, f"{type(exc).__name__}: {exc}"))
    return checks


def _dist_check(dist: str, *, required: bool, extra: str | None) -> Check:
    try:
        return Check(dist, True, importlib.metadata.version(dist), required)
    except importlib.metadata.PackageNotFoundError:
        hint = (
            f"missing; pip install 'pypos-framework[{extra}]'"
            if extra
            else "missing; pip install pypos-framework"
        )
        return Check(dist, False, hint, required)
