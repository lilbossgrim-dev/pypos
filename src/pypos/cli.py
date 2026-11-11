"""``pypos`` command-line interface (requires the ``cli`` extra: Typer)."""

from __future__ import annotations

import json
import sys
from typing import Any

from pypos import __version__, ops
from pypos.exceptions import PyPOSError


def build_app(pos_factory: Any = None) -> Any:
    """Create the Typer app. ``pos_factory`` lets tests inject a ready POS."""
    import typer

    app = typer.Typer(name="pypos", help="PyPOS point-of-sale framework.", no_args_is_help=True,
                      add_completion=False)  # fmt: skip
    make_pos = pos_factory or (lambda: ops.build_pos())

    def fail(exc: Exception) -> Any:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    @app.command()
    def version() -> None:
        """Print the PyPOS version."""
        typer.echo(__version__)

    @app.command("config-check")
    def config_check() -> None:
        """Validate the configuration read from PYPOS_* variables."""
        try:
            cfg = ops.load_config()
        except PyPOSError as exc:
            fail(exc)
        typer.echo(json.dumps(cfg.redacted(), indent=2))
        problems = ops.validate_config(cfg)
        for p in problems:
            typer.secho(f"warning: {p}", fg=typer.colors.YELLOW, err=True)
        typer.secho("configuration is valid", fg=typer.colors.GREEN)

    @app.command()
    def status() -> None:
        """Show system status (database reachability, modules, payment methods)."""
        try:
            pos = make_pos()
            data = ops.system_status(pos)
        except PyPOSError as exc:
            fail(exc)
        typer.echo(json.dumps(data, indent=2, default=str))
        if data["status"] != "ok":
            raise typer.Exit(code=1)

    @app.command("db-upgrade")
    def db_upgrade(revision: str = typer.Option("head", help="target revision")) -> None:
        """Apply database migrations (Alembic) to PYPOS_DATABASE_URL."""
        try:
            pos = make_pos()
            ops.run_migrations(pos.config, revision, pos.plugin_migrations)
        except PyPOSError as exc:
            fail(exc)
        typer.secho(f"database is at {revision}", fg=typer.colors.GREEN)

    @app.command()
    def modules() -> None:
        """List core modules and installed plugins."""
        try:
            rows = make_pos().modules()
        except PyPOSError as exc:
            fail(exc)
        for r in rows:
            typer.echo(f"{r['kind']:<7} {r['name']:<12} {r['version']}")

    @app.command("create-admin")
    def create_admin(
        username: str = typer.Option(..., prompt=True),
        password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True,
                                     envvar="PYPOS_ADMIN_PASSWORD"),
    ) -> None:  # fmt: skip
        """Create the initial administrator (password is prompted, never echoed)."""
        try:
            user = ops.create_admin(make_pos(), username, password)
        except PyPOSError as exc:
            fail(exc)
        typer.secho(f"administrator {user.username!r} created", fg=typer.colors.GREEN)

    @app.command()
    def doctor() -> None:
        """Diagnose installation problems."""
        bad = 0
        for c in ops.doctor():
            mark = "ok " if c.ok else ("FAIL" if c.required else "opt ")
            typer.echo(f"[{mark}] {c.name:<15} {c.detail}")
            bad += 0 if c.ok or not c.required else 1
        raise typer.Exit(code=1 if bad else 0)

    try:  # commands contributed by plugins
        for name, func in make_pos().plugin_commands.items():
            app.command(name)(func)
    except Exception:  # a broken environment must not hide the built-in commands
        pass
    return app


def main() -> None:
    try:
        import typer  # noqa: F401
    except ImportError:
        print("the pypos CLI needs Typer: pip install 'pypos-framework[cli]'", file=sys.stderr)
        raise SystemExit(2) from None
    build_app()()


if __name__ == "__main__":  # pragma: no cover
    main()
