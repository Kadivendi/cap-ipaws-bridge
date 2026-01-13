#!/usr/bin/env python3
"""
Lightweight database admin helper referenced by ``data/README.md``.

The bridge keeps a small SQLite metadata store (``data/audit.sqlite``) for
audit / dedup state when Postgres isn't available. This script provides
``init`` / ``stats`` / ``reset`` subcommands so operators don't need to learn
the schema by reading the source.

Usage::

    python etc/db_admin.py init                 # create tables
    python etc/db_admin.py stats                # row counts per table
    python etc/db_admin.py reset --tables=audit # truncate selected tables
    python etc/db_admin.py vacuum               # run SQLite VACUUM
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(os.environ.get("BRIDGE_DB", "data/audit.sqlite"))

SCHEMA = {
    "audit_events": """
        CREATE TABLE IF NOT EXISTS audit_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id      TEXT    NOT NULL,
            event_type    TEXT    NOT NULL,
            source        TEXT,
            destination   TEXT,
            status        TEXT,
            error_message TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "dedup_entries": """
        CREATE TABLE IF NOT EXISTS dedup_entries (
            hash       TEXT PRIMARY KEY,
            alert_id   TEXT NOT NULL,
            first_seen TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "delivery_attempts": """
        CREATE TABLE IF NOT EXISTS delivery_attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id    TEXT NOT NULL,
            channel     TEXT NOT NULL,
            attempt     INTEGER NOT NULL,
            status      TEXT NOT NULL,
            duration_ms INTEGER,
            attempted_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
}


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(db_path: Path) -> None:
    with _connect(db_path) as conn:
        for name, ddl in SCHEMA.items():
            conn.execute(ddl)
            logger.info("ensured table %s", name)
        conn.commit()


def stats(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        logger.warning("%s does not exist yet — run `init` first", db_path)
        return {}
    out: dict[str, int] = {}
    with _connect(db_path) as conn:
        for name in SCHEMA:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()
                out[name] = int(row["n"])
            except sqlite3.OperationalError as exc:
                logger.warning("could not read %s: %s", name, exc)
                out[name] = -1
    return out


def reset(db_path: Path, tables: list[str]) -> None:
    if not db_path.exists():
        logger.warning("%s does not exist; nothing to reset", db_path)
        return
    with _connect(db_path) as conn:
        for name in tables:
            if name not in SCHEMA:
                logger.warning("unknown table %r — skipping", name)
                continue
            conn.execute(f"DELETE FROM {name}")
            logger.info("truncated %s", name)
        conn.commit()


def vacuum(db_path: Path) -> None:
    if not db_path.exists():
        logger.warning("%s does not exist; nothing to vacuum", db_path)
        return
    with _connect(db_path) as conn:
        conn.execute("VACUUM")
        logger.info("vacuumed %s", db_path)


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="etc/db_admin.py")
    p.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help=f"Path to SQLite file (default: {DEFAULT_DB})",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Create the audit / dedup / delivery tables.")
    sub.add_parser("stats", help="Print row counts per table.")
    r = sub.add_parser("reset", help="Truncate one or more tables.")
    r.add_argument(
        "--tables", required=True,
        help=f"Comma-separated table names (one of: {','.join(SCHEMA)})",
    )
    sub.add_parser("vacuum", help="Run SQLite VACUUM on the file.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    db_path: Path = args.db

    if args.cmd == "init":
        init_schema(db_path)
    elif args.cmd == "stats":
        counts = stats(db_path)
        for name, n in counts.items():
            print(f"{name:24s} {n:>10d}")
    elif args.cmd == "reset":
        reset(db_path, [t.strip() for t in args.tables.split(",") if t.strip()])
    elif args.cmd == "vacuum":
        vacuum(db_path)
    else:  # pragma: no cover — argparse guarantees a known cmd
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
