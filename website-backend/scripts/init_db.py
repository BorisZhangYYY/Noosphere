"""
init_db.py - Database initialisation helper

Resets the target database to a clean state, re-applies all schema migrations,
and seeds a default admin user.

Usage
-----
    # Use conf/global.conf defaults (recommended)
    python website-backend/scripts/init_db.py

    # Override specific fields
    python website-backend/scripts/init_db.py \
        --conf website-backend/conf/global.conf \
        --admin-username admin \
        --admin-password Admin1234! \
        --admin-email admin@example.com

    # Dry-run: show what would happen without executing
    python website-backend/scripts/init_db.py --dry-run

Steps performed
---------------
1. Connect to the database defined in global.conf (or via CLI flags).
2. Take an automatic backup snapshot to backups/ before touching anything.
3. Drop all application tables (user_info, schema_migrations) so we start fresh.
4. Re-run all versioned migrations via migration.py → rebuilds the full schema.
5. Seed one default admin user (username / password / email configurable).
6. Print a summary of what was done.

Safety
------
- Requires explicit --yes flag (or interactive confirmation) to prevent
  accidental data loss in production.
- Always creates a backup snapshot first (uses pg_snapshot.py logic).
- Never hard-codes credentials; reads from conf or environment variables.
"""
from __future__ import annotations

import argparse
import os
import sys
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Make sure the backend root is on sys.path so we can import app modules
# even when the script is run from the project root.
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # scripts/
BACKEND_DIR = SCRIPT_DIR.parent                        # website-backend/
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Config loading  (mirrors pg_snapshot.py approach)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    user: str
    password: str
    db: str


def _read_conf(conf_path: Path) -> dict[str, str]:
    if not conf_path.exists():
        return {}
    parser = ConfigParser()
    parser.read(conf_path)
    if not parser.has_section("postgres"):
        return {}
    return {k: v for k, v in parser.items("postgres")}


def load_pg_config(
    conf_path: Path,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    db: Optional[str] = None,
) -> PgConfig:
    data = _read_conf(conf_path)
    return PgConfig(
        host=host     or data.get("host")     or os.getenv("POSTGRES_HOST", "localhost"),
        port=port     or int(data.get("port") or os.getenv("POSTGRES_PORT", "5432")),
        user=user     or data.get("user")     or os.getenv("POSTGRES_USER", "postgres"),
        password=password or data.get("password") or os.getenv("POSTGRES_PASSWORD", ""),
        db=db         or data.get("db")       or os.getenv("POSTGRES_DB", "postgres"),
    )


# ---------------------------------------------------------------------------
# Snapshot helper  (re-uses pg_snapshot.export_db)
# ---------------------------------------------------------------------------

def _take_backup(cfg: PgConfig, backup_dir: Path) -> Path:
    """Export a full SQL snapshot before we touch anything."""
    # Import here so the script can still run even if pg_snapshot has issues
    from scripts.pg_snapshot import export_db, PgConfig as SnapshotCfg  # type: ignore[import]

    snap_cfg = SnapshotCfg(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        db=cfg.db,
    )
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = backup_dir / f"{cfg.db}-before-init-{ts}.sql"
    backup_dir.mkdir(parents=True, exist_ok=True)
    export_db(snap_cfg, out)
    return out


# ---------------------------------------------------------------------------
# Core reset + seed logic
# ---------------------------------------------------------------------------

DROP_TABLES_SQL = """
DROP TABLE IF EXISTS user_info CASCADE;
DROP TABLE IF EXISTS schema_migrations CASCADE;
"""


def _reset_schema(dsn: str, dry_run: bool) -> None:
    """Drop all application tables so migrations start from zero."""
    import psycopg  # type: ignore[import]

    print("[init] Dropping existing tables (user_info, schema_migrations)…")
    if dry_run:
        print(f"[dry-run] Would execute:\n{DROP_TABLES_SQL.strip()}")
        return
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(DROP_TABLES_SQL)
    print("[init] Tables dropped.")


def _run_migrations(dry_run: bool) -> None:
    """Re-apply all versioned migrations via the app's migration module."""
    print("[init] Running schema migrations…")
    if dry_run:
        print("[dry-run] Would call run_migrations() — skipped.")
        return

    # We need a Flask app context because get_db_connection() reads current_app.config
    from run import app  # type: ignore[import]
    from app.db.migration import run_migrations  # type: ignore[import]

    with app.app_context():
        run_migrations()
    print("[init] Migrations applied.")


def _seed_admin(
    dsn: str,
    username: str,
    password: str,
    email: str,
    dry_run: bool,
) -> None:
    """Insert the default admin user."""
    import psycopg  # type: ignore[import]
    from app.auth.passwords import hash_password  # type: ignore[import]
    from app.auth.validation import validate_username, validate_password, validate_email  # type: ignore[import]

    # Validate inputs before touching the DB
    ok, msg = validate_username(username)
    if not ok:
        print(f"[error] Invalid admin username: {msg}")
        sys.exit(1)

    ok, msg = validate_password(password)
    if not ok:
        print(f"[error] Invalid admin password: {msg}")
        sys.exit(1)

    ok, msg = validate_email(email)
    if not ok:
        print(f"[error] Invalid admin email: {msg}")
        sys.exit(1)

    pw_hash = hash_password(password)

    insert_sql = """
    INSERT INTO user_info (username, password_hash, email, is_active, email_verified)
    VALUES (%s, %s, %s, TRUE, TRUE)
    RETURNING id;
    """

    print(f"[init] Seeding default admin user '{username}' <{email}>…")
    if dry_run:
        print(f"[dry-run] Would insert admin user '{username}' — skipped.")
        return

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(insert_sql, (username, pw_hash, email))
            row = cur.fetchone()
    user_id = int(row[0]) if row else "?"
    print(f"[init] Admin user created  →  id={user_id}  username={username}  email={email}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_CONF = BACKEND_DIR / "conf" / "global.conf"
DEFAULT_BACKUP_DIR = BACKEND_DIR / "backups"

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin1234!"
DEFAULT_ADMIN_EMAIL    = "admin@example.com"


def _confirm(prompt: str) -> bool:
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="init_db",
        description="Reset the database, re-run migrations, and seed a default admin user.",
    )
    parser.add_argument("--conf",     default=str(DEFAULT_CONF), help="Path to global.conf")
    parser.add_argument("--host",     default=None)
    parser.add_argument("--port",     type=int, default=None)
    parser.add_argument("--user",     default=None, help="DB role / superuser for connection")
    parser.add_argument("--password", default=None)
    parser.add_argument("--db",       default=None, help="Target database name")

    parser.add_argument("--admin-username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    parser.add_argument("--admin-email",    default=DEFAULT_ADMIN_EMAIL)

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the automatic pre-reset backup snapshot",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making any changes",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip interactive confirmation prompt",
    )

    args = parser.parse_args()

    cfg = load_pg_config(
        conf_path=Path(args.conf),
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        db=args.db,
    )

    # Build psycopg DSN string
    auth = f"{cfg.user}:{cfg.password}@" if cfg.password else f"{cfg.user}@"
    dsn = f"postgresql://{auth}{cfg.host}:{cfg.port}/{cfg.db}"

    # ── Summary banner ──────────────────────────────────────────────────────
    print("=" * 60)
    print("  init_db — Database Reset & Seed")
    print("=" * 60)
    print(f"  Target   : {cfg.db} @ {cfg.host}:{cfg.port}")
    print(f"  DB user  : {cfg.user}")
    print(f"  Admin    : {args.admin_username} <{args.admin_email}>")
    print(f"  Backup   : {'SKIPPED (--no-backup)' if args.no_backup else str(DEFAULT_BACKUP_DIR)}")
    print(f"  Dry-run  : {args.dry_run}")
    print("=" * 60)
    print()
    print("⚠️  WARNING: This will DROP all existing data in the database.")
    print()

    if not args.dry_run and not args.yes:
        if not _confirm("Type 'yes' to continue, anything else to abort: "):
            print("[aborted] No changes were made.")
            return 0

    # ── Step 1: Backup ──────────────────────────────────────────────────────
    if not args.no_backup and not args.dry_run:
        print("[init] Taking backup snapshot before reset…")
        try:
            snap_path = _take_backup(cfg, DEFAULT_BACKUP_DIR)
            print(f"[init] Backup saved → {snap_path}")
        except Exception as exc:
            print(f"[warning] Backup failed ({exc}). Continuing anyway.")
    else:
        if args.dry_run:
            print("[dry-run] Would take backup snapshot — skipped.")

    # ── Step 2: Drop tables ─────────────────────────────────────────────────
    _reset_schema(dsn, dry_run=args.dry_run)

    # ── Step 3: Re-run migrations ───────────────────────────────────────────
    _run_migrations(dry_run=args.dry_run)

    # ── Step 4: Seed admin user ─────────────────────────────────────────────
    _seed_admin(
        dsn=dsn,
        username=args.admin_username,
        password=args.admin_password,
        email=args.admin_email,
        dry_run=args.dry_run,
    )

    # ── Done ────────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    if args.dry_run:
        print("  [dry-run complete] No changes were made.")
    else:
        print("  ✅  Database initialised successfully.")
        print()
        print(f"  Default admin credentials:")
        print(f"    Username : {args.admin_username}")
        print(f"    Password : {args.admin_password}")
        print(f"    Email    : {args.admin_email}")
        print()
        print("  ⚠️  Change the admin password after first login!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
