"""Regression coverage for real Auctionator 340 market formats and failures."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from goblin_eye.auction_policy import configure_market, market_profile
from goblin_eye.config import Settings
from goblin_eye.ingestion.auctionator import (
    AuctionatorCapture, AuctionatorSavedVariablesAdapter, AuctionatorWatcher,
    parse_auctionator_file, select_auctionator_markets,
)
from goblin_eye.repository import Database
from goblin_eye.services import ResearchService

ROOT = Path(__file__).resolve().parents[1]


class AuctionatorFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / 'test.db')
        self.db.migrate(ROOT / 'migrations')
        self.path = Path(self.temp.name) / 'Auctionator.lua'
        self.path.write_bytes(b'fixture')

    def profile(self):
        with self.db.transaction() as c:
            return market_profile(c)

    def test_mixed_serialized_and_literal_tables_decode_without_executing_lua(self):
        # CBOR {version: 2, "4306": {m: 100}}; no personal fixture is committed.
        cbor = b'\xa2\x67version\x02\x644306\xa1\x61m\x18\x64'
        escaped = ''.join('\\%03d' % byte for byte in cbor)
        self.path.write_text('AUCTIONATOR_PRICE_DATABASE = { ["__dbversion"] = 8, '
            '["TestRealm"] = "' + escaped + '", ["PvP"] = { ["version"] = 2, '
            '["4306"] = { ["m"] = 200, ["h"] = {[2467] = 200} } } }\n'
            'AUCTIONATOR_POSTING_HISTORY = {}', encoding='utf-8')
        capture = parse_auctionator_file(self.path)
        self.assertEqual(capture.markets['TestRealm']['4306']['m'], 100)
        self.assertEqual(capture.markets['PvP']['4306']['h'], {2467: 200})
        self.path.write_text('AUCTIONATOR_PRICE_DATABASE = {["__dbversion"]=8,["PvP"]=os.execute("bad")}\nAUCTIONATOR_POSTING_HISTORY = {}')
        with self.assertRaisesRegex(ValueError, 'Unsupported Lua expression'):
            parse_auctionator_file(self.path)

    def test_normalized_realm_imports_and_unmatched_bucket_does_not_abort(self):
        configure_market(self.db, Settings(local_realm='Test Realm', local_faction='alliance'))
        capture = AuctionatorCapture(1790980000, 8, {
            'TestRealm': {'version': 2, '4306': {'m':100, 'h':{2467:100}}},
            'PvP': {'version': 2, '4306': {'m':900, 'h':{2467:900}}},
        })
        with patch('goblin_eye.ingestion.auctionator.parse_auctionator_file', return_value=capture):
            result = AuctionatorSavedVariablesAdapter().import_file(self.db, self.path)
        self.assertEqual(result.records, 1)
        self.assertIn('PvP', result.warnings[0])
        self.assertEqual(self.profile()['ruleset'], 'unknown')
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT current_min_unit_copper FROM price_observations').fetchone()[0], 100)

    def test_explicit_ruleset_prefers_regional_storage_over_old_realm_prices(self):
        configure_market(self.db, Settings(local_realm='Test Realm', local_faction='horde', local_ruleset='pvp'))
        selected, skipped = select_auctionator_markets({'TestRealm': {}, 'PvP': {}, 'RP': {}}, self.profile())
        self.assertEqual(list(selected), ['PvP'])
        self.assertEqual(set(skipped), {'TestRealm', 'RP'})
        self.assertEqual(selected['PvP'][1], 'unknown')

    def test_buckets_do_not_infer_ruleset_or_faction_or_accept_wrong_realm(self):
        configure_market(self.db, Settings(local_realm='Test Realm'))
        with self.assertRaisesRegex(ValueError, 'local_ruleset'):
            select_auctionator_markets({'PvP': {}, 'OtherRealm': {}}, self.profile())
        self.assertEqual(self.profile()['ruleset'], 'unknown')
        self.assertEqual(self.profile()['faction'], 'unknown')

    def test_all_supported_rulesets_match_only_the_configured_bucket(self):
        for ruleset, key in [('normal','PvE'), ('pvp','PvP'), ('rp','RP')]:
            profile = dict(self.profile(), realm='Test Realm', ruleset=ruleset)
            selected, _ = select_auctionator_markets({'PvE':{}, 'PvP':{}, 'RP':{}, 'HC':{}}, profile)
            self.assertEqual(list(selected), [key])

    def test_unchanged_failure_backs_off_and_health_exposes_it_before_any_source(self):
        watcher = AuctionatorWatcher(self.db, lambda: [self.path])
        with patch.object(watcher.adapter, 'import_file', side_effect=ValueError('Bad saved market')) as call:
            watcher.scan_once()
            watcher.scan_once()
            self.assertEqual(call.call_count, 1)
            health = ResearchService(self.db, Settings()).sources()
            self.assertEqual(health['file_import_error_count'], 1)
            self.assertEqual(health['watched_files'][0]['last_error'], 'Bad saved market')
            self.assertFalse(any(s['source_key']=='local-auctionator' for s in health['sources']))
            self.path.write_bytes(b'changed')
            watcher.scan_once()
            self.assertEqual(call.call_count, 2)
            configure_market(self.db, Settings(local_realm='Test Realm'))
            watcher.scan_once()
            self.assertEqual(call.call_count, 3)
            with patch('goblin_eye.ingestion.auctionator.time.monotonic', return_value=float('inf')):
                watcher.scan_once()
            self.assertEqual(call.call_count, 4)

    def test_success_after_failure_clears_diagnostic_and_does_not_reimport(self):
        configure_market(self.db, Settings(local_realm='Test Realm'))
        watcher = AuctionatorWatcher(self.db, lambda: [self.path])
        watcher.scan_once()
        self.assertEqual(ResearchService(self.db, Settings()).sources()['file_import_error_count'], 1)
        capture = AuctionatorCapture(1790980000,8,{'TestRealm':{'version':2,'4306':{'m':100,'h':{2467:100}}}})
        self.path.write_bytes(b'changed')
        with patch('goblin_eye.ingestion.auctionator.parse_auctionator_file', return_value=capture) as parse:
            watcher.scan_once()
            watcher.scan_once()
            self.assertEqual(parse.call_count, 1)
        self.assertEqual(ResearchService(self.db, Settings()).sources()['file_import_error_count'], 0)


if __name__ == '__main__':
    unittest.main()
