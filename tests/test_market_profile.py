from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest
from unittest.mock import patch

from goblin_eye.config import Settings
from goblin_eye.repository import Database
from goblin_eye import auction_policy

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-03T00:00:00+00:00"


class LocalMarketProfileTests(unittest.TestCase):
    """A fresh database must not assert any player's faction, ruleset or region."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / "test.db")
        self.db.migrate(ROOT / "migrations")

    def add_source(self, key="local-ahledger"):
        with self.db.transaction() as connection:
            return connection.execute(
                "INSERT INTO sources(source_key,name,source_type,trust_rank) VALUES (?,'Local','local_addon',1)",
                (key,)).lastrowid

    def profile(self):
        with self.db.transaction() as connection:
            return auction_policy.market_profile(connection)

    def test_fresh_database_leaves_identity_unknown(self):
        profile = self.profile()
        self.assertEqual(profile["faction"], "unknown")
        self.assertEqual(profile["ruleset"], "unknown")
        self.assertEqual(profile["region"], "unknown")
        self.assertEqual(profile["realm"], "unknown")
        self.assertEqual(profile["legacy_unverified"], 0)

    def test_configured_identity_is_recorded(self):
        auction_policy.configure_market(self.db, Settings(
            local_faction="alliance", local_ruleset="normal", local_region="eu", local_realm="Some Realm"))
        profile = self.profile()
        self.assertEqual(profile["faction"], "alliance")
        self.assertEqual(profile["ruleset"], "normal")
        self.assertEqual(profile["region"], "eu")
        self.assertEqual(profile["realm"], "Some Realm")

    def test_unknown_configuration_does_not_overwrite_evidence(self):
        auction_policy.configure_market(self.db, Settings(local_faction="horde"))
        auction_policy.configure_market(self.db, Settings(local_realm="Another Realm"))
        profile = self.profile()
        self.assertEqual(profile["faction"], "horde")
        self.assertEqual(profile["realm"], "Another Realm")
        self.assertEqual(profile["ruleset"], "unknown")

    def test_source_reported_fields_are_merged_and_persisted(self):
        source_id = self.add_source()
        with self.db.transaction() as connection:
            market_id = auction_policy.local_market(connection, source_id, NOW, "1.60.1",
                                                   faction="Horde", region="US", realm="Real Realm")
            row = connection.execute(
                "SELECT market_key,faction,ruleset,region FROM markets WHERE id=?", (market_id,)).fetchone()
        self.assertEqual(row["market_key"], "wow-forever")
        self.assertEqual(row["faction"], "horde")
        self.assertEqual(row["ruleset"], "unknown")
        self.assertEqual(row["region"], "us")
        self.assertEqual(self.profile()["realm"], "Real Realm")

    def test_conflicting_identity_is_refused_and_retained(self):
        auction_policy.configure_market(self.db, Settings(local_faction="horde"))
        with self.db.transaction() as connection:
            with self.assertRaises(ValueError) as raised:
                auction_policy.local_market(connection, self.add_source(), NOW, faction="Alliance")
            self.assertIn("separate database", str(raised.exception))
        self.assertEqual(self.profile()["faction"], "horde")

    def test_legacy_upgrade_preserves_rows_and_allows_repeated_new_imports(self):
        old_migrations = Path(self.temp.name) / 'old_migrations'
        old_migrations.mkdir()
        for migration in (ROOT / 'migrations').glob('*.sql'):
            if migration.name < '020':
                shutil.copyfile(migration, old_migrations / migration.name)
        old_db = Database(Path(self.temp.name) / 'old.db')
        old_db.migrate(old_migrations)
        with old_db.transaction() as c:
            source = c.execute("INSERT INTO sources(source_key,name,source_type,trust_rank) VALUES ('local-ahledger','Local','local_addon',1)").lastrowid
            market = c.execute("INSERT INTO markets(market_key,name,region,ruleset,faction,is_verified,source_id,retrieved_at,confidence,evidence_kind) VALUES ('wow-forever','Old','unknown','pvp','horde',0,?,?,0.9,'observed')", (source, NOW)).lastrowid
            snapshot = c.execute("INSERT INTO snapshots(external_id,market_id,captured_at,source_id,is_complete,confidence,evidence_kind,imported_at) VALUES ('old-scan',?,?,?,0,0.9,'observed',?)", (market, NOW, source, NOW)).lastrowid
            c.execute("INSERT INTO auction_rows VALUES (?,1,4306,2,1000,0,1)", (snapshot,))
            c.execute("INSERT INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body) VALUES (?,'old-ref',?,'application/json','old-hash',?)", (source, NOW, b'{"realm":"old"}'))
        old_db.migrate(ROOT / 'migrations')
        auction_policy.configure_market(old_db, Settings(local_faction='alliance', local_realm='New Realm'))
        with old_db.transaction() as c:
            for _ in range(2):
                fresh = auction_policy.local_market(c, source, NOW, faction='Alliance', realm='New Realm')
            self.assertNotEqual(market, fresh)
            self.assertEqual(c.execute('SELECT market_id FROM snapshots WHERE id=?', (snapshot,)).fetchone()[0], market)
            self.assertEqual(tuple(c.execute('SELECT item_id,quantity,buyout_copper FROM auction_rows').fetchone()), (4306,2,1000))
            self.assertEqual(c.execute('SELECT body FROM source_documents').fetchone()[0], b'{"realm":"old"}')
            legacy = c.execute('SELECT market_key,faction,ruleset,region FROM markets WHERE id=?', (market,)).fetchone()
            self.assertEqual(tuple(legacy), ('wow-forever-legacy','unknown','unknown','unknown'))
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(auction_policy.context(old_db)['legacy_market_key'], 'wow-forever-legacy')

    def scan_file(self, scans):
        rows = []
        for scan in scans:
            rows.append('{' + ','.join(f'[{json.dumps(key)}]={json.dumps(value) if type(value) is not bool else str(value).lower()}' for key, value in scan.items()) + '}')
        path = Path(self.temp.name) / 'AHledger.lua'
        path.write_text('AHledgerDB = {\n["version"] = 2,\n["scans"] = {' + ','.join(rows) + '}\n}', encoding='utf-8')
        return path

    def scan(self, realm, faction, ts, price, region='EU'):
        return dict(realm=realm,faction=faction,region=region,ts=ts,build='1.60.1',addon='0.4.6',full=True,count=1,data=f'4306:2:{price}:0:1')

    def test_ahledger_mixed_saved_scans_import_only_configured_profile(self):
        from goblin_eye.ingestion.ahledger_local import LocalAHLedgerAdapter
        auction_policy.configure_market(self.db, Settings(local_realm='Selected',local_faction='alliance',local_region='eu'))
        path = self.scan_file([self.scan('Selected','Alliance',1790980000,1000),
                               self.scan('Selected','Horde',1790980010,9000),
                               self.scan('Elsewhere','Alliance',1790980020,8000),
                               self.scan('Selected','Alliance',1790980030,7000,'US')])
        result = LocalAHLedgerAdapter().import_file(self.db, path)
        self.assertEqual(result.records, 1)
        self.assertTrue(any('Skipped 3' in note for note in result.warnings))
        with self.db.transaction() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT buyout_copper FROM auction_rows')], [1000])
        self.assertEqual(LocalAHLedgerAdapter().import_file(self.db, path).records, 0)

    def test_unconfigured_ahledger_chooses_newest_eligible_scan(self):
        from goblin_eye.ingestion.ahledger_local import LocalAHLedgerAdapter
        path = self.scan_file([self.scan('Old','Horde',1790980000,9000),
                               self.scan('New','Alliance',1790980010,1000)])
        self.assertEqual(LocalAHLedgerAdapter().import_file(self.db,path).records, 1)
        self.assertEqual(self.profile()['realm'], 'New')
        self.assertEqual(self.profile()['faction'], 'alliance')

    def test_auctionator_filters_other_realms_without_aborting_selected_prices(self):
        from goblin_eye.ingestion.auctionator import AuctionatorCapture, AuctionatorSavedVariablesAdapter
        auction_policy.configure_market(self.db, Settings(local_realm='Selected',local_faction='alliance'))
        path = Path(self.temp.name) / 'Auctionator.lua'
        path.write_bytes(b'fixture')
        capture = AuctionatorCapture(1790980000,8,{'Selected Alliance': {'version':2,'4306':{'m':1000,'h':{'2466':1000}}},
                                                  'Selected Horde': {'version':2,'4306':{'m':9000,'h':{'2466':9000}}}})
        with patch('goblin_eye.ingestion.auctionator.parse_auctionator_file',return_value=capture):
            result = AuctionatorSavedVariablesAdapter().import_file(self.db,path)
        self.assertEqual(result.records, 1)
        with self.db.transaction() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT current_min_unit_copper FROM price_observations')], [1000])

    def test_late_configuration_updates_market_metadata(self):
        source = self.add_source()
        with self.db.transaction() as c:
            market = auction_policy.local_market(c,source,NOW,faction='Alliance',realm='Selected')
        auction_policy.configure_market(self.db,Settings(local_region='eu',local_ruleset='rp'))
        with self.db.transaction() as c:
            self.assertEqual(tuple(c.execute('SELECT region,ruleset FROM markets WHERE id=?',(market,)).fetchone()), ('eu','rp'))

    def test_ambiguous_auctionator_profile_retains_database_and_explains_selection(self):
        from goblin_eye.ingestion.auctionator import AuctionatorCapture, AuctionatorSavedVariablesAdapter
        path = Path(self.temp.name) / 'Auctionator.lua'
        path.write_bytes(b'fixture')
        capture = AuctionatorCapture(1790980000,8,{'A Alliance': {'version':2},'B Horde': {'version':2}})
        with patch('goblin_eye.ingestion.auctionator.parse_auctionator_file',return_value=capture):
            with self.assertRaisesRegex(ValueError, 'local_realm and local_faction'):
                AuctionatorSavedVariablesAdapter().import_file(self.db,path)
        self.assertEqual(self.profile()['realm'], 'unknown')
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM markets').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM price_observations').fetchone()[0], 0)

    def test_context_reports_unknown_identity_before_any_scan(self):
        context = auction_policy.context(self.db)
        self.assertEqual(context["market_key"], "wow-forever")
        self.assertEqual(context["name"], "WoW Forever")
        for key in ("faction", "ruleset", "region", "realm"):
            self.assertEqual(context[key], "unknown")
        self.assertEqual(context["public_feed"]["source_key"], "ahledger")
        self.assertIsNone(context["public_feed"]["preferred_reference"])

    def test_context_prefers_the_matching_public_market(self):
        public_source_id = self.add_source("ahledger")
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO markets(market_key,name,region,ruleset,faction,is_verified,source_id,retrieved_at,confidence,evidence_kind) "
                "VALUES ('forever.normal.alliance.eu','WoW Forever · Normal Alliance EU (community)',"
                "'eu','normal','alliance',1,?,?,0.9,'observed')", (public_source_id, NOW))
        auction_policy.configure_market(self.db, Settings(
            local_faction="alliance", local_ruleset="normal", local_region="eu"))
        context = auction_policy.context(self.db)
        self.assertEqual(context["public_feed"]["preferred_reference"], "forever.normal.alliance.eu")

    def test_settings_reject_an_unreviewed_faction_or_ruleset(self):
        for field, value in (("local_faction", "Horde"), ("local_faction", "blood-elf"),
                             ("local_ruleset", "pvp2"), ("local_region", "us-west")):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    Settings(**{field: value})


if __name__ == "__main__":
    unittest.main()
