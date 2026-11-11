"""Optional HTTP API (FastAPI). The core never imports this package's heavy parts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pypos.exceptions import ConfigurationError

if TYPE_CHECKING:
    from pypos.application import POS


def _require_fastapi() -> None:
    try:
        import fastapi  # noqa: F401
    except ImportError as exc:
        raise ConfigurationError(
            "the HTTP API needs FastAPI: pip install 'pypos-framework[api]'"
        ) from exc


def create_app(pos: POS, **kwargs: Any) -> Any:
    """Build the FastAPI application for ``pos`` (requires the ``api`` extra)."""
    _require_fastapi()
    from pypos.api.app import create_app as _create

    return _create(pos, **kwargs)


def context_dependency(pos: POS) -> Any:
    """Auth dependency for plugin routes (requires the ``api`` extra)."""
    _require_fastapi()
    from pypos.api.app import context_dependency as _dep

    return _dep(pos)


__all__ = ["context_dependency", "create_app"]
