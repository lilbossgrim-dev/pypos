"""ASGI entry point for servers: ``uvicorn --factory pypos.api.asgi:create``.

Configuration comes from ``PYPOS_*`` environment variables (see docs/configuration.md).
Plugins advertised under the ``pypos.plugins`` entry-point group are loaded automatically.
"""

from typing import Any

from pypos import ops
from pypos.api import create_app


def create() -> Any:
    pos = ops.build_pos()
    pos.initialize()
    return create_app(pos)
