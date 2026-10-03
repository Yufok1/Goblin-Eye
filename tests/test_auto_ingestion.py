from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch, Mock

from goblin_eye.config import Settings
from goblin_eye.repository import Database
from goblin_eye.ingestion import discovery
from goblin_eye.ingestion.base import AdapterCapability, ImportResult
from goblin_eye.ingestion.static_watcher import StaticAddonWatcher
from goblin_eye.ingestion.foreverguide import ForeverGuideWatcher
from goblin_eye.ingestion.foreverguide_dungeons import parse_foreverguide_dungeons
from goblin_eye.ingestion.official import BlizzardResearchWatcher

ROOT = Path(__file__).resolve().parents[1]


class AutoImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "test.db")
        self.db.migrate(ROOT / "migrations")

    def test_existing_configuration_enables_new_sources_and_resolves_paths(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"mapzeroth_paths": ["addons/Mapzeroth"]}))
        settings = Settings.load(config)
        self.assertTrue(settings.auto_import_questiedb)
        self.assertTrue(settings.auto_import_mapzeroth)
        self.assertTrue(settings.auto_sync_official)
        self.assertEqual(settings.mapzeroth_paths, (str((self.root / "addons/Mapzeroth").resolve()),))
        config.write_text('{"auto_import_questiedb": "yes"}')
        with self.assertRaises(ValueError):
            Settings.load(config)

    def test_discovery_does_not_require_auctionator_or_professiondb(self):
        addon = self.root / "_classic_beta_/Interface/AddOns/Mapzeroth"
        addon.mkdir(parents=True)
        (addon / "Mapzeroth.toc").write_text("test")
        saved = self.root / "_classic_beta_/WTF/Account/TEST/SavedVariables/AHledger.lua"
        saved.parent.mkdir(parents=True)
        saved.write_text("test")
        with patch.object(discovery, "WOW_ROOTS", (self.root,)):
            self.assertEqual(discovery.discover_addon_paths("Mapzeroth", "Mapzeroth.toc"), [addon.resolve()])
            from goblin_eye.ingestion.ahledger_local import discover_local_scans
            self.assertEqual(discover_local_scans(), [saved.resolve()])

    def make_watcher(self):
        watcher = StaticAddonWatcher(self.db, (str(self.root),))
        watcher.addon, watcher.marker = "Test", "Test.toc"
        watcher.files = ("Test.toc",)
        watcher.source_key, watcher.source_type, watcher.rank = "test-source", "test", 4
        watcher.adapter = Mock()
        watcher.adapter.capability = AdapterCapability("test", "Test", "ready", (), (), (), "https://example.com")
        def success(*args):
            with self.db.transaction() as connection:
                connection.execute("""INSERT INTO sources(source_key,name,source_type,trust_rank,last_success_at)
                    VALUES ('test-source','Test','test',4,'2026-10-03') ON CONFLICT(source_key)
                    DO UPDATE SET last_error=NULL,last_success_at=excluded.last_success_at""")
            return ImportResult("test", "test-source", 1, 0)
        watcher.adapter.import_file.side_effect = success
        (self.root / "Test.toc").write_text("initial")
        return watcher, success

    def test_unchanged_skipped_change_imported_failure_retried(self):
        watcher, success = self.make_watcher()
        self.assertEqual(len(watcher.scan_once()), 1)
        self.assertEqual(watcher.scan_once(), [])
        (self.root / "Test.toc").write_text("changed source contents")
        watcher.adapter.import_file.side_effect = ValueError("partial update")
        with self.assertLogs(level="ERROR"):
            self.assertEqual(watcher.scan_once(), [])
        with self.db.transaction() as connection:
            self.assertEqual(connection.execute("SELECT last_error FROM sources").fetchone()[0], "partial update")
        watcher.adapter.import_file.side_effect = success
        self.assertEqual(len(watcher.scan_once()), 1)
        self.assertEqual(watcher.scan_once(), [])
        with self.db.transaction() as connection:
            self.assertIsNone(connection.execute("SELECT last_error FROM sources").fetchone()[0])

    def test_first_failure_is_visible(self):
        watcher, _ = self.make_watcher()
        watcher.adapter.import_file.side_effect = ValueError("bad format")
        with self.assertLogs(level="ERROR"):
            watcher.scan_once()
        with self.db.transaction() as connection:
            row = connection.execute("SELECT last_success_at,last_error FROM sources").fetchone()
            self.assertIsNone(row[0])
            self.assertEqual(row[1], "bad format")

    def test_foreverguide_failure_does_not_poison_other_catalogs(self):
        names = ("ForeverGuide.toc", "README.txt", "ItemSearchData.lua", "ItemSearch.lua", "ProfessionData.lua",
                 "Professions.lua", "Auction.lua", "DungeonLoot.lua", "DungeonData.lua", "Dungeons.lua")
        for name in names:
            (self.root / name).write_text("test")
        from goblin_eye.ingestion.foreverguide import ForeverGuideAdapter
        from goblin_eye.ingestion.foreverguide_professions import ForeverGuideProfessionAdapter
        from goblin_eye.ingestion.foreverguide_dungeons import ForeverGuideDungeonAdapter
        watcher = ForeverGuideWatcher(self.db, (str(self.root),))
        with patch.object(discovery, "WOW_ROOTS", ()), \
             patch.object(ForeverGuideAdapter, "import_file", return_value="acquisition") as acquisition, \
             patch.object(ForeverGuideProfessionAdapter, "import_file", return_value="professions") as professions, \
             patch.object(ForeverGuideDungeonAdapter, "import_file", side_effect=ValueError("dungeon only")) as dungeon:
            self.assertEqual(watcher.scan_once(), ["acquisition", "professions"])
            self.assertEqual(watcher.scan_once(), [])
            self.assertEqual(acquisition.call_count, 1)
            self.assertEqual(professions.call_count, 1)
            self.assertEqual(dungeon.call_count, 2)
        with self.db.transaction() as connection:
            rows = connection.execute("SELECT source_key,last_error FROM sources").fetchall()
            self.assertEqual([tuple(row) for row in rows], [("foreverguide-dungeons", "dungeon only")])

    def dungeon_fixture(self, quest_id):
        files = {
            "ForeverGuide.toc": "## Interface: 16001\n## Version: test\n",
            "DungeonLoot.lua": "-- foreverchanges.pro boss loot\nns.LOOT = {}",
            "DungeonData.lua": '-- QuestieDB (Forever) + foreverchanges.pro\nns.DQ = {[' + quest_id +
                ']={n="Quest",rw={fv=true,c={{123,1}}}}}',
            "Dungeons.lua": "rw and rw.fv", "ItemSearch.lua": "fv = q.rw.fv",
        }
        for name, body in files.items():
            (self.root / name).write_text(body)

    def test_synthetic_quests_retained_without_fabricated_ids(self):
        self.dungeon_fixture('"n:excavation-site:H:Quest"')
        data = parse_foreverguide_dungeons(self.root)
        self.assertEqual(data["counts"]["name_only_quests"], 1)
        self.assertEqual(data["edges"], ())
        self.assertIn("n:excavation", data["files"]["DungeonData.lua"].decode())
        self.dungeon_fixture("42")
        self.assertEqual(len(parse_foreverguide_dungeons(self.root)["edges"]), 1)
        for invalid in ("-1", '"unknown:Quest"'):
            self.dungeon_fixture(invalid)
            with self.assertRaises(ValueError):
                parse_foreverguide_dungeons(self.root)

    def test_official_first_failure_is_visible_and_retried(self):
        watcher = BlizzardResearchWatcher(self.db)
        with patch.object(watcher.adapter, "sync", side_effect=[ValueError("offline"), "recovered"]):
            self.assertIsNone(watcher.scan_once())
            self.assertEqual(watcher.scan_once(), "recovered")
        with self.db.transaction() as connection:
            self.assertEqual(connection.execute("SELECT last_error FROM sources").fetchone()[0], "offline")


if __name__ == "__main__":
    unittest.main()
