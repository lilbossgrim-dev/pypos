# PyPOS

**A modular, typed point-of-sale framework for Python.** Build retail, grocery, hardware, stationery, café or multi-branch POS applications on top of ready-made inventory, sales, payments, cash-drawer, returns and reporting services — without re-implementing the commercial rules every time.

> **Project status: alpha (0.1.0).** The in-memory backend, domain services, plugin system and test-suite are verified. The SQLAlchemy/PostgreSQL backend, Alembic migrations, FastAPI integration and Typer CLI are written and covered by tests that run where those libraries are installed — see [docs/development-status.md](docs/development-status.md) for exactly what was and was not executed. Do not use it for real money before you have run the full suite against your own PostgreSQL.

> **Placeholders:** this repository belongs to [lilbossgrim-dev](https://github.com/lilbossgrim-dev) and is named `pypos`. The LICENSE copyright information is © 2026 lilbossgrim-dev. See [Making it yours](#making-it-yours).

## Table of contents

[What it is](#what-it-is) · [Features](#features) · [Architecture](#architecture) · [Requirements](#requirements) · [Installation](#installation) · [Quick start](#quick-start) · [Configuration](#configuration) · [Database](#database) · [Modules](#modules) · [Payments](#payments) · [Plugins](#plugins--extending-pypos) · [HTTP API](#http-api-optional) · [CLI](#cli) · [Testing](#testing) · [Security](#security) · [Contributing](#contributing) · [License](#license) · [Limitations](#limitations)

## What it is

Most POS projects start by re-implementing the same hard parts: exact money arithmetic, stock that never goes silently negative, atomic sales, idempotent retries, cash-drawer reconciliation, refunds. PyPOS provides those as a library with a small public API. Your application imports the services, wires its own UI/API/hardware, and extends the framework through plugins instead of forking it.

## Features

- **Exact money**: `Money` on `Decimal`, explicit rounding, floats rejected everywhere, allocation without losing a cent.
- **Products**: SKU, multiple barcodes, categories, variants, units (fractional kg/l), search/filter/pagination, CSV import/export (all-or-nothing).
- **Inventory**: per-warehouse stock, receipts/issues/adjustments, transfers, physical counts, minimum stock, negative-stock policy, full movement history, idempotent movements, optimistic concurrency (and row locks on PostgreSQL).
- **Sales**: carts, line/sale discounts, inclusive or exclusive taxes, snapshots so history never changes, sequential receipt numbers, receipts and audited reprints, confirmation/cancellation, **persistent idempotency**.
- **Payments**: cash, split payments, adapter interface for external providers, refunds, reconciliation, sandbox adapter clearly labelled. External charges are never "rolled back" by a DB transaction — failures are compensated.
- **Cash drawer**: opening float, pay-in/out, withdrawals, interim counts, closing with differences, history.
- **Returns**: partial/total, quantity control, authorization threshold, restock, refund tracking and retry, duplicate prevention.
- **Customers, suppliers, purchasing**: contacts, purchase orders, partial receipts, cost updates.
- **Users & permissions**: roles, fine-grained permissions (`sales.cancel`, `payments.refund`, …), scrypt password hashing, lockout, signed expiring tokens, branch restrictions, merchant isolation.
- **Audit log** written in the same transaction as each change.
- **Reports** with CSV export.
- **Plugins**: services, collections, events, CLI commands, HTTP routes, config, dependency ordering, cycle detection, version compatibility.
- **Optional** FastAPI HTTP API and Typer CLI; the core never needs them.

## Architecture

```
            your app / UI / hardware            HTTP API (optional)      CLI (optional)
                       │                              │                       │
                       └──────────────┬───────────────┴───────────────────────┘
                                      ▼
                         POS  (composition root, plugins)
                                      │
   products · inventory · sales · payments · cash · returns · purchasing · users · reporting …
                    (services = all business rules, permission checks, audit)
                                      │  Transaction / Collection[T]
                          ┌───────────┴────────────┐
                    MemoryStore               SQLStore (SQLAlchemy 2.x)
                  (tests, demos)              PostgreSQL / SQLite + Alembic
```

Details: [docs/architecture.md](docs/architecture.md).

## Requirements

- Python **3.11+** (CI matrix: 3.11, 3.12, 3.13).
- Core dependencies: `pydantic`, `SQLAlchemy 2.x`, `alembic`, `packaging`.
- Optional extras: `api` (FastAPI, uvicorn), `cli` (Typer), `postgres` (psycopg), `docs` (MkDocs Material), `dev` (pytest, pytest-cov, ruff, mypy, httpx, build).

## Installation

### Clone your repository

```bash
git clone https://github.com/lilbossgrim-dev/pypos.git
cd pypos
```

### Create and activate a virtual environment

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
# if scripts are blocked:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Install

Development mode (editable) with everything you need to work on PyPOS:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,api,cli,docs]"
```

Library use with optional extras only when you need them:

```bash
python -m pip install .                 # core
python -m pip install ".[api]"          # + FastAPI HTTP API
python -m pip install ".[cli]"          # + `pypos` command
python -m pip install ".[postgres]"     # + PostgreSQL driver (psycopg 3)
python -m pip install ".[api,cli,postgres]"
```

PowerShell: quote the extras exactly as above (`".[dev,api]"`).

### Verify

```bash
python -m pytest            # run the test-suite
pypos doctor                # diagnose the installation (needs the cli extra)
```

## Quick start

This is `examples/basic_pos.py`, which runs as-is.

```python
"""The smallest complete POS: configure, stock a product, sell it in cash, print the receipt."""

from pypos import POS, POSConfig
from pypos.payments import PaymentRequest

config = POSConfig(database_url="memory://", currency="MXN", timezone="America/Mexico_City")
pos = POS(config=config)
pos.initialize()

root = pos.system_context()  # trusted context for setup code
branch = pos.branches.create_branch(root, "MAIN", "Corner Store")
warehouse = pos.branches.create_warehouse(root, branch.id, "WH1", "Shelf")
terminal = pos.branches.create_terminal(root, branch.id, warehouse.id, "T1", "Till 1")
ctx = root.with_location(branch.id, terminal.id)

pos.taxes.create_rule(ctx, "VAT", "VAT", "16")  # rates are data you configure
coffee = pos.products.create(ctx, "COFFEE", "Coffee 250g", "89.90", "55.00", tax_codes=["VAT"])
pos.inventory.receive(ctx, coffee.id, warehouse.id, 12)

pos.cash.open(ctx, opening_float="200.00")
cart = pos.sales.create_cart(ctx)
pos.sales.add_line(ctx, cart.id, sku="COFFEE", quantity=2)
sale = pos.sales.confirm(ctx, cart.id, [PaymentRequest("cash", "208.57", tendered="250.00")])

print(pos.sales.receipt(ctx, sale.id))
assert str(sale.total) == "208.57 MXN"
assert pos.inventory.stock_of(ctx, coffee.id, warehouse.id) == 10
print("stock left:", pos.inventory.stock_of(ctx, coffee.id, warehouse.id))
```

More runnable examples live in [`examples/`](examples/): products, inventory, sales, cash management, split payments, returns, permissions, the HTTP API and a plugin.

## Configuration

```python
from pypos import POSConfig

config = POSConfig(
    database_url="postgresql+psycopg://user:password@localhost/pos",
    currency="MXN",
    timezone="America/Mexico_City",
    secret_key="<at least 32 random characters>",  # only needed for API tokens
)
# or from the environment:  POSConfig.from_env()   (PYPOS_DATABASE_URL, PYPOS_CURRENCY, …)
```

Copy `.env.example` to `.env` for local settings (never commit it). Every option is described in [docs/configuration.md](docs/configuration.md).

## Database

| `database_url` | Use |
|---|---|
| `memory://` | Tests, demos, single-process tools. Data is lost on exit. |
| `sqlite:///store.db` | Local development. |
| `postgresql+psycopg://…` | **Production target.** |

For SQL databases create the schema with migrations (production) or let PyPOS create it (`auto_create_schema=True`, development):

```bash
export PYPOS_DATABASE_URL="postgresql+psycopg://user:password@localhost/pos"   # PowerShell: $env:PYPOS_DATABASE_URL="..."
pypos db-upgrade
```

Run PostgreSQL locally with Docker: copy `.env.example` to `.env`, set `POSTGRES_PASSWORD` and `PYPOS_SECRET_KEY`, then `docker compose up --build`.

## Modules

| Module | Entry point | Highlights |
|---|---|---|
| Products | `pos.products` | SKU, barcodes, variants, units, search, CSV |
| Inventory | `pos.inventory` | stock, movements, transfers, counts, low stock |
| Sales | `pos.sales` | carts, discounts, taxes, confirm/cancel, receipts |
| Payments | `pos.payments` | adapters, split, refunds, reconciliation |
| Cash | `pos.cash` | sessions, movements, counts, closing |
| Returns | `pos.returns` | partial/total, authorization, refunds |
| Customers / Suppliers | `pos.customers`, `pos.suppliers` | contacts, history |
| Purchasing | `pos.purchasing` | purchase orders, partial receipts |
| Taxes | `pos.taxes` | configurable rules (no built-in rates) |
| Users | `pos.users` | roles, permissions, tokens |
| Branches | `pos.branches` | branches, warehouses, terminals |
| Reporting | `pos.reporting` | reports + CSV |
| Audit | `pos.audit` | append-only trail |

Every mutating call takes an `OperationContext` (who, which branch/terminal, which permissions): `ctx = pos.context_for(user_id, branch_id=..., terminal_id=...)`. Trusted setup code can use `pos.system_context()`.

## Payments

- `cash` is built in. Any other method needs a registered adapter: `pos.payments.register_adapter("card", MyGatewayAdapter())`.
- With no adapter, a card payment **fails with an error**; PyPOS never pretends to charge.
- `SandboxAdapter` is a clearly labelled test double (`payment.sandbox=True`, receipts print "SANDBOX PAYMENT - NOT A REAL CHARGE"). `ManualReferenceAdapter` only *records* an approval made on a separate terminal; it cannot verify it.
- PyPOS does not store card numbers or CVV, and its payment models have no card-number or CVV field. Never put card data in free-form `metadata` or in your adapters.
- A database transaction cannot undo an external charge. See [docs/payments.md](docs/payments.md) for the charge → record → compensate protocol and for reconciliation.

## Plugins / extending PyPOS

```python
from pypos.plugins import Plugin, PluginRegistry


class HelloPlugin(Plugin):
    name = "hello"
    version = "1.0.0"
    requires_pypos = ">=0.1,<1"

    def register(self, registry: PluginRegistry) -> None:
        registry.on("sale.confirmed", lambda event: print("sold!", event.payload["total"]))


pos = POS(config, plugins=[HelloPlugin()])
```

Plugins can add services, collections (tables), event handlers, CLI commands, HTTP routes and migrations. A complete example (loyalty points) is in [`examples/plugins/loyalty.py`](examples/plugins/loyalty.py); the contract is in [docs/plugins.md](docs/plugins.md). Third-party packages can advertise plugins under the `pypos.plugins` entry-point group.

## HTTP API (optional)

```bash
python -m pip install ".[api]"
uvicorn --factory pypos.api.asgi:create      # needs PYPOS_* environment variables
# OpenAPI docs: http://127.0.0.1:8000/docs
```

Versioned (`/v1`), bearer-token auth, permission checks, structured errors, pagination, health checks (`/health`, `/health/ready`), idempotency via the `Idempotency-Key` header. The endpoints call the same services as Python code. See [docs/api.md](docs/api.md).

## CLI

```bash
pypos version
pypos config-check          # validate PYPOS_* configuration
pypos status                # database reachability, modules, payment methods
pypos db-upgrade            # apply Alembic migrations
pypos modules               # core modules and plugins
pypos create-admin          # prompts for username and password (hidden)
pypos doctor                # diagnose installation problems
```

## Testing

```bash
python -m pytest                              # everything available in your environment
python -m pytest --cov=pypos --cov-report=term-missing
ruff check . && ruff format --check .
mypy
mkdocs build --strict
```

Tests that need SQLAlchemy, FastAPI or Typer are skipped (and reported as skipped) when those packages are missing; CI installs them. See [docs/testing.md](docs/testing.md).

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md). Highlights: scrypt password hashing, constant-time comparisons, signed expiring tokens, account lockout, secrets masked in `repr`/logs, no secrets in the repository, permission checks in every service. Read [docs/security.md](docs/security.md) before going to production.

## Contributing

Bug reports, ideas and pull requests are welcome: [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SUPPORT.md](SUPPORT.md), [GOVERNANCE.md](GOVERNANCE.md). Documentation index: [docs/index.md](docs/index.md) (`mkdocs serve` to browse locally).

## Making it yours

1. Create an empty repository on GitHub, then in this folder run:

   `git init && git add . && git commit -m "Initial import" && git branch -M main && git remote add origin https://github.com/lilbossgrim-dev/pypos.git && git push -u origin main`.

2. Update the remaining project information:
   - GitHub user: `lilbossgrim-dev`
   - Repository: `pypos`
   - Repository URL: `https://github.com/lilbossgrim-dev/pypos`
   - Copyright year: `2026`
   - Copyright holder: `lilbossgrim-dev`
   - Author in `pyproject.toml` and `CITATION.cff`: `lilbossgrim-dev`
   - `<SECURITY_CONTACT>` in `SECURITY.md`: replace with your security contact email.
   - Update the contact information in `CODE_OF_CONDUCT.md`.

3. Enable GitHub private vulnerability reporting (Settings → Security) and let the CI workflow run.

## License

[MIT](LICENSE).

## Limitations

PyPOS does not guarantee fiscal/tax compliance in any jurisdiction (rates and rules are your data), does not include a UI, receipt-printer drivers or payment-provider integrations, and its SQL search/list operations load documents in Python (fine for thousands of products, not millions). The full, honest list is in [docs/development-status.md](docs/development-status.md).
