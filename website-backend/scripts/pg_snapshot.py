"""
pg_snapshot.py - PostgreSQL snapshot export/import helper

Usage
-----
- Export (dump the database to a SQL file)
    python website-backend/scripts/pg_snapshot.py export \
      --conf website-backend/conf/global.conf \
      [--host HOST --port PORT --user USER --password PASS --db DB] \
      [--out /path/to/dump.sql]

- Import (restore the SQL file into a target database)
    python website-backend/scripts/pg_snapshot.py import \
      --conf website-backend/conf/global.conf \
      [--host HOST --port PORT --user USER --password PASS --db DB] \
      --in /path/to/dump.sql

Behavior
--------
- By default, reads [postgres] from website-backend/conf/global.conf.
  CLI arguments override values when provided.
- Import step verifies and aligns the target environment with conf:
  * Ensures role USER exists (creates it and sets password if needed).
  * Ensures database DB exists and is owned by USER (creates/changes owner).
- Requires pg_dump and psql to be available in PATH.
- Passwords are passed via PGPASSWORD, never echoed to the console.

Examples
--------
- Export using conf defaults:
    python website-backend/scripts/pg_snapshot.py export \
      --conf website-backend/conf/global.conf \
      --out /tmp/hot_knowledge.sql

- Import on another machine:
    python website-backend/scripts/pg_snapshot.py import \
      --conf website-backend/conf/global.conf \
      --in /tmp/hot_knowledge.sql
"""
from __future__ import annotations
 

import argparse
import os
import subprocess
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import shlex

@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    user: str
    password: str
    db: str


def _read_conf(conf_path: Path) -> Dict[str, str]:
    if not conf_path.exists():
        return {}
    parser = ConfigParser()
    parser.read(conf_path)
    if not parser.has_section("postgres"):
        return {}
    return {k: v for k, v in parser.items("postgres")}


def load_pg_config(
    conf_path: Path,
    host: Optional[str],
    port: Optional[int],
    user: Optional[str],
    password: Optional[str],
    db: Optional[str],
) -> PgConfig:
    data = _read_conf(conf_path)
    return PgConfig(
        host=host or data.get("host") or os.getenv("POSTGRES_HOST", "localhost"),
        port=port or int(data.get("port") or os.getenv("POSTGRES_PORT", "5432")),
        user=user or data.get("user") or os.getenv("POSTGRES_USER", "postgres"),
        password=password or data.get("password") or os.getenv("POSTGRES_PASSWORD", ""),
        db=db or data.get("db") or os.getenv("POSTGRES_DB", "postgres"),
    )


def _env_with_password(password: str) -> Dict[str, str]:
    env = dict(os.environ)
    if password:
        env["PGPASSWORD"] = password
    return env


def export_db(cfg: PgConfig, out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pg_dump",
        "--host",
        cfg.host,
        "--port",
        str(cfg.port),
        "--username",
        cfg.user,
        "--dbname",
        cfg.db,
        "--format",
        "plain",
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "--file",
        str(out_file),
    ]
    subprocess.run(cmd, check=True, env=_env_with_password(cfg.password))


def import_db(cfg: PgConfig, in_file: Path) -> None:
    if not in_file.exists():
        raise FileNotFoundError(str(in_file))
    cmd = [
        "psql",
        "--host",
        cfg.host,
        "--port",
        str(cfg.port),
        "--username",
        cfg.user,
        "--dbname",
        cfg.db,
        "--set",
        "ON_ERROR_STOP=on",
        "--file",
        str(in_file),
    ]
    subprocess.run(cmd, check=True, env=_env_with_password(cfg.password))


def _run_psql(sql: str, *, user: str, db: str, host: str, port: int, password: str) -> subprocess.CompletedProcess:
    cmd = [
        "psql",
        "--host",
        host,
        "--port",
        str(port),
        "--username",
        user,
        "--dbname",
        db,
        "--no-align",
        "--tuples-only",
        "--command",
        sql,
    ]
    return subprocess.run(cmd, check=False, env=_env_with_password(password), capture_output=True, text=True)


def _can_connect(user: str, db: str, host: str, port: int, password: str) -> bool:
    proc = _run_psql("SELECT 1;", user=user, db=db, host=host, port=port, password=password)
    return proc.returncode == 0


def _ensure_role_and_db(cfg: PgConfig) -> None:
    # Try connecting as cfg.user first; if fails, try 'postgres' superuser without password as a common default.
    candidates = [
        (cfg.user, "postgres", cfg.password),
        ("postgres", "postgres", os.getenv("PGPASSWORD", "")),
    ]
    admin_user = None
    admin_pw = ""
    for user, db, pw in candidates:
        if _can_connect(user=user, db=db, host=cfg.host, port=cfg.port, password=pw):
            admin_user = user
            admin_pw = pw
            break
    if admin_user is None:
        raise RuntimeError(
            "Cannot connect to target PostgreSQL to prepare role/database. "
            "Tried: user=<cfg.user> and user=postgres. Configure credentials or set PGPASSWORD."
        )

    # Ensure role exists
    check_role = _run_psql(
        f"SELECT 1 FROM pg_roles WHERE rolname = {shlex.quote(cfg.user)!s};",
        user=admin_user,
        db="postgres",
        host=cfg.host,
        port=cfg.port,
        password=admin_pw,
    )
    role_exists = check_role.returncode == 0 and "1" in check_role.stdout
    if not role_exists:
        pw_clause = f" PASSWORD {shlex.quote(cfg.password)}" if cfg.password else ""
        create_role_sql = f"CREATE ROLE {cfg.user} LOGIN{pw_clause};"
        print(f"[info] Creating role '{cfg.user}'")
        proc = _run_psql(create_role_sql, user=admin_user, db="postgres", host=cfg.host, port=cfg.port, password=admin_pw)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to create role {cfg.user}: {proc.stderr.strip()}")
    else:
        if cfg.password:
            alter_sql = f"ALTER ROLE {cfg.user} WITH LOGIN PASSWORD {shlex.quote(cfg.password)};"
            _run_psql(alter_sql, user=admin_user, db="postgres", host=cfg.host, port=cfg.port, password=admin_pw)

    # Ensure database exists and ownership
    check_db = _run_psql(
        f"SELECT 1 FROM pg_database WHERE datname = {shlex.quote(cfg.db)!s};",
        user=admin_user,
        db="postgres",
        host=cfg.host,
        port=cfg.port,
        password=admin_pw,
    )
    db_exists = check_db.returncode == 0 and "1" in check_db.stdout
    if not db_exists:
        print(f"[info] Creating database '{cfg.db}' owned by '{cfg.user}'")
        create_db_sql = f"CREATE DATABASE {cfg.db} OWNER {cfg.user};"
        proc = _run_psql(create_db_sql, user=admin_user, db="postgres", host=cfg.host, port=cfg.port, password=admin_pw)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to create database {cfg.db}: {proc.stderr.strip()}")
    else:
        # Ensure ownership
        owner_q = _run_psql(
            f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = {shlex.quote(cfg.db)!s};",
            user=admin_user,
            db="postgres",
            host=cfg.host,
            port=cfg.port,
            password=admin_pw,
        )
        owner = owner_q.stdout.strip()
        if owner and owner != cfg.user:
            print(f"[info] Changing owner of database '{cfg.db}' from '{owner}' to '{cfg.user}'")
            _run_psql(
                f"ALTER DATABASE {cfg.db} OWNER TO {cfg.user};",
                user=admin_user,
                db="postgres",
                host=cfg.host,
                port=cfg.port,
                password=admin_pw,
            )


def main() -> int:
    parser = argparse.ArgumentParser(prog="pg_snapshot")
    sub = parser.add_subparsers(dest="command", required=True)

    default_conf = Path(__file__).resolve().parents[1] / "conf" / "global.conf"

    export_p = sub.add_parser("export")
    export_p.add_argument("--conf", default=str(default_conf))
    export_p.add_argument("--host", default=None)
    export_p.add_argument("--port", type=int, default=None)
    export_p.add_argument("--user", default=None)
    export_p.add_argument("--password", default=None)
    export_p.add_argument("--db", default=None)
    export_p.add_argument("--out", default=None)

    import_p = sub.add_parser("import")
    import_p.add_argument("--conf", default=str(default_conf))
    import_p.add_argument("--host", default=None)
    import_p.add_argument("--port", type=int, default=None)
    import_p.add_argument("--user", default=None)
    import_p.add_argument("--password", default=None)
    import_p.add_argument("--db", default=None)
    import_p.add_argument("--in", dest="in_file", required=True)

    args = parser.parse_args()
    cfg = load_pg_config(
        conf_path=Path(args.conf),
        host=getattr(args, "host", None),
        port=getattr(args, "port", None),
        user=getattr(args, "user", None),
        password=getattr(args, "password", None),
        db=getattr(args, "db", None),
    )

    if args.command == "export":
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / "backups" / f"{cfg.db}-{ts}.sql"
        export_db(cfg, out)
        print(str(out))
        return 0

    if args.command == "import":
        print("[info] Verifying target matches conf (role/database)...")
        _ensure_role_and_db(cfg)
        print("[info] Importing SQL file...")
        import_db(cfg, Path(args.in_file))
        print("[info] Import completed")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
