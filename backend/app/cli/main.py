"""Project CLI: `pfc <command>`. Keeps operations project-local and explicit."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import typer
from sqlalchemy import text

from app.config import BACKEND_ROOT, PROJECT_ROOT, settings
from app.database.base import SessionLocal, engine
from app.models import Base
from app.utils.dates import today_in

app = typer.Typer(
    add_completion=False,
    help="Personal Finance Companion CLI (backend, database and operations).",
    no_args_is_help=True,
)

DB_CONTAINER = os.environ.get("DB_CONTAINER", "pfc-db")
BACKUPS_DIR = PROJECT_ROOT / "backups"


def _ok(message: str) -> None:
    typer.secho(f"  OK  {message}", fg=typer.colors.GREEN)


def _warn(message: str) -> None:
    typer.secho(f" WARN {message}", fg=typer.colors.YELLOW)


def _fail(message: str) -> None:
    typer.secho(f" FAIL {message}", fg=typer.colors.RED)


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


@app.command()
def migrate() -> None:
    """Apply database migrations (Alembic upgrade head)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT
    )
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
    _ok("Database is up to date.")


@app.command("seed-demo")
def seed_demo(
    remove: bool = typer.Option(False, "--remove", help="Remove the demo account and its data."),
    yes: bool = typer.Option(False, "--yes", help="Skip the removal confirmation."),
) -> None:
    """Create or remove clearly-flagged demo data (never mixed with real data)."""
    from app.cli.demo import remove_demo, seed_demo as seed, demo_summary

    with SessionLocal() as db:
        if remove:
            if not yes and not typer.confirm("Delete ALL demo users and their financial data?"):
                raise typer.Exit(1)
            removed = remove_demo(db, settings.demo_user_email)
            _ok(f"Removed {removed} demo account(s).")
            return
        user = seed(
            db,
            email=settings.demo_user_email,
            password=settings.demo_user_password,
            timezone=settings.default_timezone,
        )
        summary = demo_summary(db, user)
    _ok("Demo data ready (flagged as demo):")
    for key, value in summary.items():
        typer.echo(f"    {key}: {value}")
    typer.echo(f"    password: {settings.demo_user_password}")


def _table_data_entries(path: Path) -> int | None:
    """Count TABLE DATA entries in a custom-format dump, or None if unreadable.

    A dump of an empty database is structurally valid but restores to nothing;
    the count is the only cheap way to tell the two apart.
    """
    command = ["docker", "exec", "-i", DB_CONTAINER, "pg_restore", "--list"]
    try:
        with path.open("rb") as handle:
            result = subprocess.run(
                command, stdin=handle, capture_output=True, timeout=120
            )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    listing = result.stdout.decode("utf-8", "ignore")
    return sum(1 for line in listing.splitlines() if " TABLE DATA " in line)


@app.command()
def backup(
    output: Path = typer.Option(None, "--output", "-o", help="Destination .dump file"),
) -> None:
    """Create a compressed PostgreSQL backup inside ./backups.

    Refuses to keep a dump that contains no table data: such a file restores
    cleanly to an empty database, which is worse than a failed backup.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    destination = output or BACKUPS_DIR / f"finance-{datetime.now():%Y%m%d-%H%M%S}.dump"
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "exec",
        DB_CONTAINER,
        "pg_dump",
        "-U",
        settings.postgres_user,
        "-Fc",
        settings.postgres_db,
    ]
    with destination.open("wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE)
    if result.returncode != 0:
        # Leave nothing behind that could be mistaken for a usable backup.
        destination.unlink(missing_ok=True)
        _fail(result.stderr.decode("utf-8", "ignore"))
        raise typer.Exit(1)

    entries = _table_data_entries(destination)
    if entries is None:
        destination.unlink(missing_ok=True)
        _fail(f"Could not verify {destination.name}; deleted it rather than keep an unchecked dump.")
        raise typer.Exit(1)
    if entries == 0:
        destination.unlink(missing_ok=True)
        _fail(
            "Refusing to keep a dump with no table data: it would restore to an empty "
            "database. Is " + DB_CONTAINER + " running with the expected data?"
        )
        raise typer.Exit(1)

    size = destination.stat().st_size
    _ok(f"Backup written to {destination} ({size / 1024:.1f} KiB, {entries} table(s) with data)")


@app.command()
def restore(
    source: Path = typer.Argument(..., exists=True, readable=True, help="Backup .dump file"),
    yes: bool = typer.Option(False, "--yes", help="Confirm replacing current data."),
) -> None:
    """Restore a backup. This REPLACES current database contents."""
    if not yes:
        typer.echo("This will replace the current database contents.")
        if not typer.confirm("Continue?"):
            raise typer.Exit(1)
    command = [
        "docker",
        "exec",
        "-i",
        DB_CONTAINER,
        "pg_restore",
        "-U",
        settings.postgres_user,
        "-d",
        settings.postgres_db,
        "--clean",
        "--if-exists",
        "--no-owner",
    ]
    with source.open("rb") as handle:
        result = subprocess.run(command, stdin=handle, stderr=subprocess.PIPE)
    if result.returncode != 0:
        _warn(result.stderr.decode("utf-8", "ignore")[:800])
        typer.echo("Restore finished with warnings (dropped objects may not exist yet).")
    else:
        _ok("Restore complete.")


@app.command()
def dev(
    host: str = typer.Option(None, "--host"),
    port: int = typer.Option(None, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Run the API server (development, auto-reload)."""
    if not _port_free(port or settings.api_port, host or settings.api_host):
        _fail(
            f"Port {port or settings.api_port} is already in use. "
            "Set API_PORT in .env or stop the other process."
        )
        raise typer.Exit(1)
    command = [
        str(Path(sys.executable).parent / "uvicorn"),
        "app.main:app",
        "--host",
        host or settings.api_host,
        "--port",
        str(port or settings.api_port),
    ]
    if reload:
        command.append("--reload")
    subprocess.run(command, cwd=BACKEND_ROOT)


@app.command()
def test(
    path: str = typer.Argument("tests"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the automated backend test suite against the test database."""
    command = [sys.executable, "-m", "pytest", path, "-q"]
    if verbose:
        command.append("-vv")
    env = {**os.environ}
    result = subprocess.run(command, cwd=BACKEND_ROOT, env=env)
    raise typer.Exit(result.returncode)


@app.command()
def doctor() -> None:
    """Check runtimes, database, migrations, configuration and ports."""
    problems = 0
    typer.echo("Runtime")
    _ok(f"Python {sys.version.split()[0]}")
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar()
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        _ok(f"PostgreSQL {version} reachable at {settings.database_url.split('@')[-1]}")
        if current:
            _ok(f"Migration revision {current}")
        else:
            _warn("No migration revision applied.")
            problems += 1
    except Exception as exc:  # noqa: BLE001 - diagnostic command
        _fail(f"Database unavailable: {exc.__class__.__name__}")
        problems += 1

    typer.echo("Configuration")
    if settings.secret_key.startswith("change-me"):
        _warn("SECRET_KEY is the example value. Generate a real one in .env.")
        problems += 1
    if settings.environment == "production" and not settings.cookie_secure:
        _warn("COOKIE_SECURE should be true in production.")
        problems += 1
    _ok(f"API http://{settings.api_host}:{settings.api_port}")
    _ok(f"Web http://{settings.web_host}:{settings.web_port}")

    typer.echo("Ports")
    for label, port in (("API", settings.api_port), ("Web", settings.web_port)):
        if _port_free(port):
            _ok(f"{label} port {port} is available")
        else:
            _warn(f"{label} port {port} is in use (may be this project already running)")

    typer.echo("Optional tooling")
    if (PROJECT_ROOT / "web" / "node_modules").exists():
        _ok("Web dependencies installed")
    else:
        _warn("Web dependencies missing: run `npm install` in web/")
    if (PROJECT_ROOT / "android" / "gradlew").exists():
        _ok("Android Gradle wrapper present")
    else:
        _warn("Android wrapper missing (see docs for Android setup)")

    if problems:
        _warn(f"{problems} issue(s) need attention.")
        raise typer.Exit(1)
    _ok("All critical checks passed.")


@app.command()
def status() -> None:
    """Show database, API and web status."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _ok("Database reachable")
    except Exception:  # noqa: BLE001
        _fail("Database unreachable")

    url = f"http://{settings.api_host}:{settings.api_port}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - loopback only
            _ok(f"API healthy ({response.status}) at {url}")
    except (urllib.error.URLError, TimeoutError, OSError):
        _fail(f"API not responding at {url}")

    web = f"http://{settings.web_host}:{settings.web_port}/"
    try:
        with urllib.request.urlopen(web, timeout=2) as response:  # noqa: S310 - loopback only
            _ok(f"Web responding ({response.status}) at {web}")
    except (urllib.error.URLError, TimeoutError, OSError):
        _warn(f"Web not responding at {web}")


@app.command()
def tables() -> None:
    """List model tables (sanity check that the schema is registered)."""
    for name in sorted(Base.metadata.tables):
        typer.echo(name)


if __name__ == "__main__":
    app()
