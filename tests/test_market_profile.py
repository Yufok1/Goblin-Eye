from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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

    def test_legacy_unverified_database_refuses_new_local_market(self):
        with self.db.transaction() as connection:
            connection.execute("UPDATE local_market_profile SET legacy_unverified=1 WHERE id=1")
        with self.db.transaction() as connection:
            with self.assertRaises(ValueError) as raised:
                auction_policy.local_market(connection, self.add_source(), NOW)
            self.assertIn("legacy", str(raised.exception))

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