"""Gate 7B Phase 0 — create the human-brain knowledge-graph databases.

Creates (idempotently, never drops) the two Gate 7B target databases:

    neurographiq_human_brain_v1       (production)
    neurographiq_human_brain_v1_e2e   (E2E test)

Connects to the ``postgres`` maintenance database because ``CREATE DATABASE``
cannot run inside a transaction against a not-yet-existing target. Never
touches the legacy ``neurographiq_kg_v3_wb`` workbench database.

Usage:
    python scripts/bootstrap_human_brain_v1.py [--host 127.0.0.1] [--port 5432]
                                                [--user postgres] [--password ...]
                                                [--maint postgres] [--check]

Credentials are read from env (PGHOST/PGPORT/PGUSER/PGPASSWORD) with the
project defaults as fallback. Passwords are never printed — logs show
``<REDACTED>``.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - environment check
    print("ERROR: psycopg (psycopg3) is required. Run: pip install psycopg[binary]")
    sys.exit(2)


MAIN_DATABASE = "neurographiq_human_brain_v1"
E2E_DATABASE = "neurographiq_human_brain_v1_e2e"
LEGACY_DATABASE = "neurographiq_kg_v3_wb"  # never touched


def _redact(secret: str | None) -> str:
    return "<REDACTED>" if secret else "<EMPTY>"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create the Gate 7B human-brain databases.")
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--password", default=os.environ.get("PGPASSWORD", "postgres"))
    p.add_argument("--maint", default="postgres", help="maintenance database name")
    p.add_argument("--check", action="store_true", help="only verify, do not create")
    return p.parse_args()


def _maintenance_conn(args: argparse.Namespace) -> psycopg.Connection:
    conn = psycopg.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=args.maint,
        autocommit=True,  # CREATE DATABASE cannot run inside a transaction
    )
    return conn


def _database_exists(conn: psycopg.Connection, dbname: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        return cur.fetchone() is not None


def _assert_legacy_untouched(conn: psycopg.Connection) -> None:
    """Guard: refuse to run if the legacy DB is not present, since we must never
    create or modify it. Merely reports presence; never connects to it."""
    exists = _database_exists(conn, LEGACY_DATABASE)
    status = "PRESENT" if exists else "MISSING"
    print(f"  legacy guard: {LEGACY_DATABASE} = {status} (read-only source, never touched)")


def bootstrap_one(conn: psycopg.Connection, dbname: str, check_only: bool) -> str:
    if _database_exists(conn, dbname):
        print(f"  {dbname}: ALREADY_EXISTS")
        return "ALREADY_EXISTS"
    if check_only:
        print(f"  {dbname}: WOULD_CREATE (check mode)")
        return "WOULD_CREATE"
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    print(f"  {dbname}: CREATED")
    return "CREATED"


def main() -> int:
    args = _parse_args()
    print("=== Gate 7B Phase 0 — bootstrap human-brain databases ===")
    print(
        f"  target: {MAIN_DATABASE}, {E2E_DATABASE}\n"
        f"  via maintenance DB: {args.maint}\n"
        f"  connection: {args.user}@{args.host}:{args.port} "
        f"(password {_redact(args.password)})"
    )

    try:
        conn = _maintenance_conn(args)
    except psycopg.OperationalError as exc:
        print(f"ERROR: cannot connect to maintenance DB '{args.maint}': {exc}")
        return 2

    try:
        _assert_legacy_untouched(conn)
        r_main = bootstrap_one(conn, MAIN_DATABASE, args.check)
        r_e2e = bootstrap_one(conn, E2E_DATABASE, args.check)
    finally:
        conn.close()

    if args.check:
        print("\n(check mode — nothing created)")
    else:
        print(
            f"\nresult: main={r_main}, e2e={r_e2e} "
            f"(scientific tables still 0 — that is Phase 1+)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
