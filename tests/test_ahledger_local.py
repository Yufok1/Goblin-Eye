import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from goblin_eye import auction_policy
from goblin_eye.config import Settings
from goblin_eye.ingestion.ahledger_local import (
    LocalAHLedgerAdapter, LocalAHLedgerWatcher, parse_scan_file,
)
from goblin_eye.repository import Database


ROOT = Path(__file__).resolve().parents[1]


class LocalAHLedgerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'AHledger.lua'
        self.db = Database(self.root / 'test.db')
        self.db.migrate(ROOT / 'migrations')

    def scan(self, **overrides):
        return dict(dict(realm='Selected', faction='Horde', region='unknown',
                         ts=1790980000, build='1.60.1 (fixture)', addon='0.15.0',
                         full=True, count=1, data='4306:2:1000:0:1'), **overrides)

    def save(self, scans):
        rows = ['{' + ','.join(f'[{json.dumps(k)}]={json.dumps(v)}' for k, v in raw.items()) + '}'
                for raw in scans]
        self.path.write_text('AHledgerDB = {\n["version"] = 2,\n["scans"] = {'
                             + ','.join(rows) + '}\n}', encoding='utf-8')

    def selected(self):
        auction_policy.configure_market(self.db, Settings(local_realm='Selected', local_faction='horde'))

    def test_blank_realm_does_not_block_identified_scans_or_change_their_provenance(self):
        self.selected()
        good = self.scan()
        unknown = self.scan(realm='', ts=1790980300, data='4306:2:9000:0:1')
        self.save([good, unknown, self.scan(realm='Other', ts=1790980200)])
        original = self.path.read_bytes()
        self.assertEqual(parse_scan_file(self.path)[1]['source'], unknown)
        result = LocalAHLedgerAdapter().import_file(self.db, self.path)
        self.assertEqual((result.records, result.snapshots), (1, 1))
        self.assertTrue(any('Skipped 1 scan(s) with missing realm/faction' in w for w in result.warnings))
        self.assertTrue(any('Skipped 1 scan(s) from other market' in w for w in result.warnings))
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT buyout_copper FROM auction_rows').fetchone()[0], 1000)
            source = c.execute("SELECT * FROM sources WHERE source_key='local-ahledger'").fetchone()
            self.assertIn('missing realm', source['notes'])
            self.assertIn('2026-10-', source['notes'])
            self.assertIsNone(source['last_error'])
            body = c.execute('SELECT body FROM source_documents').fetchone()[0]
            self.assertEqual(json.loads(body), good)
            snapshot = c.execute('SELECT * FROM snapshots').fetchone()
            self.assertEqual(snapshot['is_complete'], 0)
            self.assertEqual(snapshot['source_complete_claim'], 1)
            self.assertNotEqual(snapshot['captured_at'], snapshot['imported_at'])
            self.assertEqual(auction_policy.market_profile(c)['region'], 'unknown')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(LocalAHLedgerAdapter().import_file(self.db, self.path).records, 0)
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM auction_rows').fetchone()[0], 1)

    def test_newest_eligible_scan_alone_establishes_unset_profile(self):
        self.save([self.scan(realm='Old', ts=1790980000),
                   self.scan(realm='New', faction='Alliance', ts=1790980100),
                   self.scan(realm='', faction='Horde', ts=1790980200),
                   self.scan(realm='Unidentified faction', faction='unknown', ts=1790980300)])
        result = LocalAHLedgerAdapter().import_file(self.db, self.path)
        self.assertEqual(result.snapshots, 1)
        with self.db.transaction() as c:
            profile = auction_policy.market_profile(c)
        self.assertEqual(profile['realm'], 'New')
        self.assertEqual(profile['faction'], 'alliance')
        self.assertEqual(profile['region'], 'unknown')
        self.assertEqual(profile['ruleset'], 'unknown')

    def test_unknown_identity_is_never_filled_from_configuration_or_other_scans(self):
        self.selected()
        scans = [self.scan(realm=value, ts=1790980000+i) for i, value in enumerate(('', ' ', 'unknown', 'UNKNOWN'))]
        scans += [self.scan(faction=value, ts=1790980100+i) for i, value in enumerate(('', ' ', 'unknown'))]
        self.save(scans)
        result = LocalAHLedgerAdapter().import_file(self.db, self.path)
        self.assertEqual((result.records, result.snapshots), (0, 0))
        self.assertTrue(any('Skipped 7' in w for w in result.warnings))
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM snapshots').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM markets').fetchone()[0], 0)
            self.assertEqual(auction_policy.market_profile(c)['realm'], 'Selected')

    def test_only_unidentified_scans_leave_fresh_profile_unset(self):
        self.save([self.scan(realm='')])
        self.assertEqual(LocalAHLedgerAdapter().import_file(self.db, self.path).snapshots, 0)
        with self.db.transaction() as c:
            profile = auction_policy.market_profile(c)
            self.assertEqual(c.execute('SELECT count(*) FROM markets').fetchone()[0], 0)
        for key in ('realm', 'faction', 'region', 'ruleset'):
            self.assertEqual(profile[key], 'unknown')

    def test_malformed_payload_is_still_rejected_atomically(self):
        self.save([self.scan()])
        LocalAHLedgerAdapter().import_file(self.db, self.path)
        cases = (dict(realm=99), dict(faction='Unexpected'), dict(region=False),
                 dict(build=''), dict(addon=''), dict(full=1), dict(count=2),
                 dict(realm='', data='not an auction row'), dict(data='4306:0:1000:0:1'))
        for changes in cases:
            with self.subTest(changes=changes):
                self.save([self.scan(ts=1790980200), self.scan(ts=1790980300, **changes)])
                with self.assertRaises(ValueError):
                    LocalAHLedgerAdapter().import_file(self.db, self.path)
                with self.db.transaction() as c:
                    self.assertEqual(c.execute('SELECT count(*) FROM snapshots').fetchone()[0], 1)

    def test_watcher_backs_off_unchanged_failures_and_recovers_immediately_on_save(self):
        self.save([self.scan(realm=1)])
        clock = [0]
        watcher = LocalAHLedgerWatcher(self.db, (str(self.path),))
        # Exercise scan_once only: no background thread or real saved-file writes.
        with patch('goblin_eye.ingestion.ahledger_local.discover_local_scans', return_value=[self.path]), \
                patch('goblin_eye.ingestion.ahledger_local.time.monotonic', side_effect=lambda: clock[0]), \
                patch('goblin_eye.ingestion.ahledger_local.parse_scan_file', wraps=parse_scan_file) as parse, \
                patch.object(self.db, 'write_transaction', wraps=self.db.write_transaction) as writes:
            with self.assertLogs(level='ERROR'):
                self.assertEqual(watcher.scan_once(), [])
            self.assertEqual(parse.call_count, 1)
            with self.db.transaction() as c:
                self.assertIn('Invalid scan text field', c.execute('SELECT last_error FROM sources').fetchone()[0])
            with self.assertNoLogs():
                for _ in range(5):
                    clock[0] = 59
                    self.assertEqual(watcher.scan_once(), [])
                self.assertEqual(parse.call_count, 1)
                clock[0] = 60
                self.assertEqual(watcher.scan_once(), [])
                self.assertEqual(parse.call_count, 2, 'unchanged failures must eventually retry')
                self.assertEqual(writes.call_count, 1, 'same error is not rewritten every retry')
                self.save([self.scan()])
                clock[0] = 61
                result = watcher.scan_once()
                self.assertEqual(result[0].snapshots, 1)
                self.assertEqual(watcher.scan_once(), [])
                self.assertEqual(parse.call_count, 3)
            with self.db.transaction() as c:
                self.assertIsNone(c.execute('SELECT last_error FROM sources').fetchone()[0])
            self.assertEqual(watcher._failures, {})

    def test_watcher_reports_changed_failure_and_retries_transient_errors(self):
        self.save([self.scan()])
        watcher = LocalAHLedgerWatcher(self.db, (str(self.path),))
        clock = [0]
        with patch('goblin_eye.ingestion.ahledger_local.discover_local_scans', return_value=[self.path]), \
                patch('goblin_eye.ingestion.ahledger_local.time.monotonic', side_effect=lambda: clock[0]), \
                patch('goblin_eye.ingestion.ahledger_local.parse_scan_file', side_effect=OSError('temporary read failure')):
            with self.assertLogs(level='ERROR'):
                watcher.scan_once()
        with patch('goblin_eye.ingestion.ahledger_local.discover_local_scans', return_value=[self.path]), \
                patch('goblin_eye.ingestion.ahledger_local.time.monotonic', side_effect=lambda: clock[0]):
            clock[0] = 60
            self.assertEqual(watcher.scan_once()[0].snapshots, 1)
            self.save([self.scan(data='broken')])
            with self.assertLogs(level='ERROR'):
                self.assertEqual(watcher.scan_once(), [])
            with self.db.transaction() as c:
                self.assertEqual(c.execute('SELECT count(*) FROM snapshots').fetchone()[0], 1)
                self.assertEqual(c.execute('SELECT last_error FROM sources').fetchone()[0], 'Unsupported packed auction row')

    def test_failed_error_write_is_retried_without_repeating_the_source_traceback(self):
        self.save([self.scan(realm=99)])
        watcher = LocalAHLedgerWatcher(self.db, (str(self.path),))
        clock = [0]
        with patch('goblin_eye.ingestion.ahledger_local.discover_local_scans', return_value=[self.path]), \
                patch('goblin_eye.ingestion.ahledger_local.time.monotonic', side_effect=lambda: clock[0]):
            with patch.object(self.db, 'write_transaction', side_effect=OSError('temporary database failure')):
                with self.assertLogs(level='ERROR') as logs:
                    self.assertEqual(watcher.scan_once(), [])
                self.assertEqual(len(logs.records), 2)
            clock[0] = 60
            with self.assertNoLogs():
                self.assertEqual(watcher.scan_once(), [])
            with self.db.transaction() as c:
                self.assertEqual(c.execute('SELECT last_error FROM sources').fetchone()[0], 'Invalid scan text field')


if __name__ == '__main__':
    unittest.main()
