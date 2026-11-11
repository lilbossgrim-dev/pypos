# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Initial public structure of PyPOS 0.1.0 (alpha): exact money type, transactional storage
  abstraction (in-memory and SQLAlchemy backends), services for products, inventory, sales,
  payments, cash management, returns, customers, suppliers, purchasing, taxation, users and
  permissions, branches, reporting, audit and receipts.
- Plugin system with dependency ordering and compatibility checks.
- Optional FastAPI application and Typer CLI.
- Alembic migration generated from the collection specs.
- Test suite, examples, documentation and CI workflow.

> Nothing has been released or published. See `docs/development-status.md` for what has and has
> not been verified.
