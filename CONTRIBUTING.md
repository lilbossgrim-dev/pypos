# Contributing to PyPOS

Thank you for helping! Bug reports, documentation fixes, tests and features are all welcome.

## Set up

```bash
git clone https://github.com/<TU_USUARIO>/<TU_REPOSITORIO>.git
cd <TU_REPOSITORIO>
python3 -m venv .venv && source .venv/bin/activate     # PowerShell: py -3 -m venv .venv; .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,api,cli,docs]"
pre-commit install                                     # optional
```

## Before opening a pull request

```bash
ruff check . && ruff format --check .
mypy
python -m pytest
mkdocs build --strict
```

`make check` runs the same steps.

## Rules of the road

- **Money is never a `float`.** Use `Decimal` / `Money`. Floats are rejected by the codec.
- Business rules live in services, never in API endpoints or the CLI.
- Every state-changing operation checks a permission and writes an audit record in the same
  transaction.
- Never store card numbers or CVV; never commit secrets.
- Add tests for every behaviour change; keep examples runnable (`tests/test_examples.py`).
- If you change a collection spec, regenerate the migration:
  `python scripts/gen_migration.py` (a test fails when they drift).
- Update `docs/` and `CHANGELOG.md` for user-visible changes. `docs/development-status.md` must
  stay honest about what is verified.

## Commits and pull requests

Small, focused pull requests with a clear description. Link the issue if there is one. By
contributing you agree that your contribution is licensed under the project's MIT license.

## Reporting security issues

Do **not** open a public issue; follow [SECURITY.md](SECURITY.md).
