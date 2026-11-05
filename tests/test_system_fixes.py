import json
from pathlib import Path
import unittest
import test_research_coverage as coverage
from goblin_eye.characters import CharacterStore
from goblin_eye.item_instances import ItemInstances
from goblin_eye.item_graph import ItemGraph
from goblin_eye.ingestion.foreverguide_dungeons import ForeverGuideDungeonAdapter
from goblin_eye.mcp_server import TOOLS


class SystemFixTests(unittest.TestCase):
    setUp = coverage.CoverageTests.setUp
    import_save = coverage.CoverageTests.import_save
    snapshot_id = coverage.CoverageTests.snapshot_id

    def test_discovery_preserves_baseline_and_quest_semantics(self):
        addon = self.path / 'ForeverGuide'
        addon.mkdir()
        files = {
            'ForeverGuide.toc': '## Interface: 16001\n## Version: fixture\n',
            'DungeonLoot.lua': '-- foreverchanges.pro boss loot\nns.LOOT={test={{n="Boss",lv="25",id=101,items={{id=201,n="Baseline"},{id=202,n="Added",new=true}}}}}',
            'DungeonData.lua': '-- QuestieDB (Forever) + foreverchanges.pro\nns.DUNGEONS={{key="test",en="Test Dungeon",q={301}}}\nns.DQ={[301]={n="Quest",lv=28,rl=20,z=999,rw={fv=true,c={{203,1}}}}}',
            'Dungeons.lua': 'rw and rw.fv', 'ItemSearch.lua': 'fv = q.rw.fv',
        }
        for name, body in files.items():
            (addon / name).write_text(body)
        ForeverGuideDungeonAdapter().import_file(self.db, addon)
        page = self.server._call('search_acquisition_sources', {'dungeon': 'Test Dungeon', 'min_level': 22, 'max_level': 32})
        self.assertEqual({r['item_id'] for r in page['records']}, {201, 202, 203})
        basis = {r['item_id']: r['evidence_basis'] for r in page['records']}
        self.assertEqual(basis[201], 'classic_baseline')
        self.assertEqual(basis[202], 'forever_community')
        self.assertEqual(self.server._call('search_acquisition_sources', {'method': 'quest_reward', 'max_level': 22})['total'], 0)
        unknown = ItemGraph(self.db).search_items('203')['items']
        self.assertEqual(unknown, [{'item_id': 203, 'name': None}])
        self.assertIsNotNone(self.server._call('get_item_research', {'item_id': 203}))
        with self.db.transaction() as c:
            ds = c.execute('SELECT id FROM research_datasets WHERE active=1').fetchone()[0]
            c.execute("INSERT INTO item_property_facts VALUES (?,201,'catalog',?,?)", (ds, json.dumps({'quality':'RARE'}), 'fixture'))
        rare = self.server._call('search_acquisition_sources', {'item_quality':'RARE'})
        self.assertEqual([r['item_id'] for r in rare['records']], [201])
        with self.db.transaction() as c:
            c.execute("INSERT INTO item_property_facts VALUES (?,201,'tooltip',?,?)", (ds, json.dumps({'quality':'UNCOMMON'}), 'fixture'))
        self.assertEqual(self.server._call('search_acquisition_sources', {'item_quality':'RARE'})['total'], 0)
        with self.db.transaction() as c:
            c.execute("UPDATE world_entity_facts SET attributes_json=? WHERE entity_type='npc'", (json.dumps({'level': '??'}),))
        self.assertEqual(self.server._call('search_acquisition_sources', {'method': 'drop', 'max_level': 32})['total'], 0)

    def test_later_item_capture_does_not_rewrite_snapshot(self):
        self.import_save()
        snapshot = self.snapshot_id()
        self.record['capturedAt'] += 60
        self.record['stats']['ITEM_MOD_INTELLECT_SHORT'] = 99
        self.import_save()
        self.assertEqual(CharacterStore(self.db).get(snapshot)['items'][0]['instance_stats']['stats']['intellect'], 7)
        self.assertEqual(ItemInstances(self.db).page(6617)['records'][0]['stats']['intellect'], 99)

    def test_kilo_manifest_matches_read_only_registry(self):
        root = Path(__file__).resolve().parents[1]
        names = json.loads((root / 'wow-ai/bridge/research-tools.json').read_text())
        self.assertEqual(names, sorted(t['name'] for t in TOOLS if t.get('annotations', {}).get('readOnlyHint') is True))


if __name__ == '__main__':
    unittest.main()
