"""Imports queue for the writer while dashboard/MCP readers stay available."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import threading
import unittest

from goblin_eye.repository import Database
from goblin_eye.ingestion.alts_forever import AltsForeverAdapter
from goblin_eye.ingestion.base import AdapterCapability
from goblin_eye.ingestion.static_watcher import StaticAddonWatcher


ROOT = Path(__file__).resolve().parents[1]


class ShortTimeoutDatabase(Database):
    def connect(self):
        connection = super().connect()
        connection.execute('PRAGMA busy_timeout=1')
        return connection


class DatabaseConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root/'test.db'
        self.db = ShortTimeoutDatabase(self.path)
        with self.db.write_transaction() as c:
            c.execute('CREATE TABLE queue_probe(value INTEGER)')

    def held_writer(self, ready, release):
        with self.db.write_transaction() as c:
            c.execute('INSERT INTO queue_probe VALUES (1)')
            ready.set()
            if not release.wait(10):
                raise TimeoutError('Test writer was not released')

    def test_writers_share_a_gate_across_instances_without_blocking_readers(self):
        ready, release, attempted, finished = (threading.Event() for _ in range(4))
        other = ShortTimeoutDatabase(self.path)

        def second_writer():
            attempted.set()
            try:
                with other.write_transaction() as c:
                    c.execute('INSERT INTO queue_probe VALUES (2)')
            finally:
                finished.set()

        def read_committed():
            # The dashboard's writable handle and the MCP's read-only handle
            # both need to read while an import is still uncommitted.
            for database in (self.db, Database(self.path, read_only=True)):
                with database.transaction() as c:
                    self.assertEqual(c.execute('SELECT count(*) FROM queue_probe').fetchone()[0], 0)

        def unrelated_database():
            with ShortTimeoutDatabase(self.root/'other.db').write_transaction() as c:
                c.execute('CREATE TABLE unrelated(value INTEGER)')

        with ThreadPoolExecutor(max_workers=3) as pool:
            holding = pool.submit(self.held_writer, ready, release)
            try:
                self.assertTrue(ready.wait(5))
                queued = pool.submit(second_writer)
                self.assertTrue(attempted.wait(5))
                # Longer than the deliberately tiny SQLite timeout: waiting
                # must happen in our queue, before opening a write transaction.
                self.assertFalse(finished.wait(.05))
                pool.submit(read_committed).result(timeout=5)
                pool.submit(unrelated_database).result(timeout=5)
            finally:
                release.set()
            holding.result(timeout=5)
            queued.result(timeout=5)
        with self.db.transaction() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT value FROM queue_probe ORDER BY value')], [1, 2])

    def test_failed_write_rolls_back_and_releases_the_gate(self):
        with self.assertRaisesRegex(ValueError, 'invalid import'):
            with self.db.write_transaction() as c:
                c.execute('INSERT INTO queue_probe VALUES (1)')
                raise ValueError('invalid import')
        with ShortTimeoutDatabase(self.path).write_transaction() as c:
            c.execute('INSERT INTO queue_probe VALUES (2)')
        with self.db.transaction() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT value FROM queue_probe')], [2])

    def test_connection_failure_releases_the_gate(self):
        from unittest.mock import patch
        with patch.object(self.db, 'connect', side_effect=sqlite3.OperationalError('open failed')):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'open failed'):
                with self.db.write_transaction():
                    self.fail('Connection should not have opened')
        with self.db.write_transaction() as c:
            c.execute('INSERT INTO queue_probe VALUES (2)')

    def test_nested_writer_fails_without_waiting_for_its_own_connection(self):
        with self.db.write_transaction() as c:
            with self.assertRaisesRegex(RuntimeError, 'reuse the active'):
                with Database(self.path).write_transaction():
                    self.fail('Nested connection should not open')
            c.execute('INSERT INTO queue_probe VALUES (1)')

    def test_read_only_handle_cannot_start_a_writer(self):
        with self.assertRaisesRegex(ValueError, 'Read-only'):
            with Database(self.path, read_only=True).write_transaction():
                self.fail('Read-only handle should not enter')

    def test_character_import_and_source_error_logging_wait_for_a_large_import(self):
        self.db.migrate(ROOT/'migrations')
        saved = self.root/'AltsForever.lua'
        saved.write_text('AltsForeverDB={v=2,chars={Fixture={name="Fixture",class="WARLOCK",'
                         'level=20,updated=1792410000,gear={}}}}')
        addon = self.root/'Broken'
        addon.mkdir()
        (addon/'Broken.toc').write_text('invalid source data')

        class BrokenAdapter:
            capability = AdapterCapability('broken', 'Broken', 'ready', (), (), (), 'https://example.com')

            def import_file(self, database, path):
                raise ValueError('invalid source data')

        class AnnouncedDatabase(ShortTimeoutDatabase):
            def __init__(self, path, attempted):
                super().__init__(path)
                self.attempted = attempted

            def write_transaction(self, **kwargs):
                self.attempted.set()
                return super().write_transaction(**kwargs)

        character_waiting, error_waiting = threading.Event(), threading.Event()
        watcher = StaticAddonWatcher(AnnouncedDatabase(self.path, error_waiting), (str(addon),))
        watcher.addon, watcher.marker, watcher.files = 'Broken', 'Broken.toc', ('Broken.toc',)
        watcher.source_key, watcher.source_type, watcher.rank = 'broken', 'test', 4
        watcher.adapter = BrokenAdapter()
        ready, release = threading.Event(), threading.Event()
        with self.assertLogs(level='ERROR') as logged, ThreadPoolExecutor(max_workers=3) as pool:
            holding = pool.submit(self.held_writer, ready, release)
            try:
                self.assertTrue(ready.wait(5))
                character = pool.submit(AltsForeverAdapter().import_file,
                                        AnnouncedDatabase(self.path, character_waiting), saved)
                error = pool.submit(watcher.scan_once)
                self.assertTrue(character_waiting.wait(5))
                self.assertTrue(error_waiting.wait(5))
                self.assertFalse(character.done())
                self.assertFalse(error.done())
            finally:
                release.set()
            holding.result(timeout=5)
            self.assertEqual(character.result(timeout=5).snapshots, 1)
            self.assertEqual(error.result(timeout=5), [])
        self.assertNotIn('database is locked', '\n'.join(logged.output))
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM character_snapshots').fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT last_error FROM sources WHERE source_key='broken'").fetchone()[0],
                             'invalid source data')


if __name__ == '__main__':
    unittest.main()
