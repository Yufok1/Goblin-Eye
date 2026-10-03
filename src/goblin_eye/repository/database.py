from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Iterator


class Database:
    def __init__(self, path: str | Path, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = (sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
                      if self.read_only else sqlite3.connect(self.path, timeout=30))
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if not self.read_only:
                # journal_mode can fail immediately during concurrent first-open,
                # even with SQLite's normal busy timeout configured.
                deadline = time.monotonic() + 10
                while True:
                    try:
                        if connection.execute('PRAGMA journal_mode').fetchone()[0] != 'wal':
                            connection.execute("PRAGMA journal_mode = WAL")
                        break
                    except sqlite3.OperationalError as exc:
                        if 'locked' not in str(exc).lower() or time.monotonic() >= deadline:
                            raise
                        time.sleep(.05)
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self, migrations_dir: str | Path) -> None:
        directory = Path(migrations_dir)
        if self.read_only:
            raise ValueError('Read-only connections cannot migrate; run goblin-eye init explicitly')
        if not directory.is_dir():
            raise ValueError('Migrations unavailable: run from a supported source checkout')
        # execute() preserves the explicit transaction; executescript() commits it.
        with self.transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            for migration in sorted(directory.glob("*.sql")):
                version = migration.stem
                connection.execute('BEGIN IMMEDIATE')
                try:
                    if not connection.execute('SELECT 1 FROM schema_migrations WHERE version=?', (version,)).fetchone():
                        statement = ''
                        for char in migration.read_text(encoding='utf-8'):
                            statement += char
                            if char == ';' and sqlite3.complete_statement(statement):
                                connection.execute(statement)
                                statement = ''
                        if statement.strip():
                            connection.execute(statement)
                        connection.execute('INSERT INTO schema_migrations VALUES (?, ?)',
                                           (version, datetime.now(timezone.utc).isoformat()))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise

    def require_ready(self, migrations_dir: str | Path) -> None:
        if not self.path.is_file():
            raise ValueError(f'Database does not exist: {self.path.resolve()}. Select the existing database or run init.')
        expected = {p.stem for p in Path(migrations_dir).glob('*.sql')}
        if not expected:
            raise ValueError('Run from the supported Goblin Eye source checkout; migrations are unavailable')
        try:
            with self.transaction() as connection:
                applied = {r[0] for r in connection.execute('SELECT version FROM schema_migrations')}
        except sqlite3.Error as exc:
            raise ValueError('Database is not initialized; run goblin-eye init') from exc
        if expected != applied:
            raise ValueError('Database schema differs from this checkout; back up and run goblin-eye init with the matching version')
