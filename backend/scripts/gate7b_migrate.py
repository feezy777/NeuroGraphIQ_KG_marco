"""Gate 7B migration runner.

Processes ONLY ``gate7b_*.sql`` files under ``backend/migrations/``, sorted by
their integer ``NNN``. It intentionally ignores the 123 legacy migrations
(``NNN_*.sql`` and friends) — those belong to the old workbench lineage.

Safety properties:
  * lexicographic + integer order (no framework)
  * duplicate ``NNN`` -> hard fail (ambiguous ordering)
  * SHA-256 checksum recorded per migration; a mismatch on a previously applied
    migration fails closed
  * idempotent: already-applied migrations are skipped
  * ``--plan`` dry-run prints what *would* run without touching the database

Usage:
    python scripts/gate7b_migrate.py [--plan] [--host 127.0.0.1] [--port 5432]
                                      [--user postgres] [--password ...]
                                      [--db neurographiq_human_brain_v1]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover - environment check
    print("ERROR: psycopg (psycopg3) is required. Run: pip install psycopg[binary]")
    sys.exit(2)


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
FILENAME_RE = re.compile(r"^gate7b_(\d{3})_.*\.sql$")
MAIN_DATABASE = "neurographiq_human_brain_v1"


def _redact(secret: str | None) -> str:
    return "<REDACTED>" if secret else "<EMPTY>"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gate 7B migration runner.")
    p.add_argument("--plan", action="store_true", help="dry-run: show plan, apply nothing")
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--password", default=os.environ.get("PGPASSWORD", "postgres"))
    p.add_argument("--db", default=MAIN_DATABASE)
    return p.parse_args()


def _discover() -> list[tuple[int, Path]]:
    """Return (NNN, path) for every gate7b_*.sql, or raise on duplicates."""
    found: dict[int, Path] = {}
    for path in sorted(MIGRATIONS_DIR.glob("gate7b_*.sql")):
        m = FILENAME_RE.match(path.name)
        if not m:
            continue
        nnn = int(m.group(1))
        if nnn in found:
            raise SystemExit(
                f"ERROR: duplicate migration NNN={nnn:03d}: "
                f"{found[nnn].name} and {path.name}"
            )
        found[nnn] = path
    return [(nnn, found[nnn]) for nnn in sorted(found)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _connect(args: argparse.Namespace) -> psycopg.Connection:
    try:
        return psycopg.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            dbname=args.db,
            autocommit=False,
        )
    except psycopg.OperationalError as exc:
        print(f"ERROR: cannot connect to target DB '{args.db}': {exc}")
        print("       run scripts/bootstrap_human_brain_v1.py first if the DB is missing.")
        sys.exit(2)


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS infra")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS infra.schema_migrations (
                migration_id    TEXT PRIMARY KEY,
                filename        TEXT NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                execution_ms    BIGINT,
                status          TEXT NOT NULL,
                remark          TEXT
            )
            """
        )
    conn.commit()


def _applied_rows(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT migration_id, checksum_sha256 FROM infra.schema_migrations ORDER BY migration_id"
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def _apply(conn: psycopg.Connection, nnn: int, path: Path, checksum: str) -> str:
    migration_id = f"gate7b_{nnn:03d}"
    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO infra.schema_migrations
                (migration_id, filename, checksum_sha256, execution_ms, status, remark)
            VALUES (%s, %s, %s, %s, 'APPLIED', NULL)
            """,
            (migration_id, path.name, checksum, elapsed_ms),
        )
    conn.commit()
    return migration_id


def main() -> int:
    args = _parse_args()
    migrations = _discover()
    if not migrations:
        print("ERROR: no gate7b_*.sql migrations found in", MIGRATIONS_DIR)
        return 2

    print("=== Gate 7B migration runner ===")
    print(
        f"  target DB: {args.db}\n"
        f"  connection: {args.user}@{args.host}:{args.port} "
        f"(password {_redact(args.password)})\n"
        f"  discovered: {len(migrations)} gate7b_*.sql file(s)"
    )

    if args.plan:
        for nnn, path in migrations:
            print(f"  [plan] gate7b_{nnn:03d}  {path.name}  sha256={_sha256(path)[:12]}…")
        print("(dry-run — nothing applied)")
        return 0

    conn = _connect(args)
    try:
        _ensure_tracking_table(conn)
        applied = _applied_rows(conn)

        for nnn, path in migrations:
            migration_id = f"gate7b_{nnn:03d}"
            checksum = _sha256(path)
            if migration_id in applied:
                if applied[migration_id] != checksum:
                    print(
                        f"ERROR: checksum mismatch for applied migration {migration_id} "
                        f"({path.name}). Refusing to continue — fail closed."
                    )
                    return 3
                print(f"  skip {migration_id}  {path.name}  (already applied)")
                continue
            print(f"  apply {migration_id}  {path.name}")
            _apply(conn, nnn, path, checksum)

        print("done.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
