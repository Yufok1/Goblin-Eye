from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from goblin_eye.repository import Database
from goblin_eye.config import Settings
from goblin_eye.services import ResearchService
from goblin_eye.characters import CharacterStore
from goblin_eye.agent_responses import prepare_response
from goblin_eye.ingestion.alts_forever import AltsForeverAdapter
from goblin_eye.ingestion.foreverguide import ForeverGuideWatcher
from goblin_eye.ingestion.foreverguide_items import ForeverGuideItemAdapter, stat_values, TOOLTIP_STATS

ROOT = Path(__file__).resolve().parents[1]


class ItemPropertyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.db = Database(self.path/'test.db')
        self.db.migrate(ROOT/'migrations')
        self.addon = self.path/'ForeverGuide'
        self.addon.mkdir()
        self.write('ForeverGuide.toc','## Interface: 16001\n## Version: fixture\n')
        self.write('ItemCatalogData.lua','-- ItemSparse/Item build 1.60.1.70170\nns.CAT_DATA = [[\n7001 2 19 26 29 0 3 4\n6903 4 1 7 28 23 2 4\n]]\nns.CAT_NAMES = {[7001]="Fixture Wand",[6903]="Fixture Pants"}\n')
        self.write('GearData.lua','-- WoWSims 1.60.1.70205\nns.GEAR_DATA = [[\n7001 26 19 24 3 0 0 spi=3,dps=29\n6903 7 1 23 2 0 0 sp=12,spi=9\n]]\n')
        self.write('ItemStatsData.lua','-- Wowhead Forever / Wowhead Classic build 1.60.1.70170\nns.ITEM_STATS = {[6903]="F\\t3\\t28\\t23\\t1\\t7\\t4\\t1\\t40\\t\\tspi=9,splpwr=12\\t",[7001]="C\\t3\\t29\\t18\\t\\t26\\t2\\t19\\t0\\t30-57@1.50\\tshares=4\\tE:Fixture effect"}\n')
        self.adapter = ForeverGuideItemAdapter()

    def write(self,name,text):
        (self.addon/name).write_text(text,encoding='utf-8')

    def test_item_tool_keeps_properties_in_compact_response_and_separates_conflicts(self):
        self.adapter.import_file(self.db,self.addon)
        service=ResearchService(self.db,Settings())
        result=prepare_response('get_item_research',service.item(6903))
        props=result['item_properties']['variants']
        self.assertEqual(result['name'],'Fixture Pants')
        self.assertEqual(props['gear']['stats']['spell_power'],12)
        self.assertEqual(props['tooltip']['stats']['spell_power'],12)
        self.assertEqual(props['catalog']['quality'],'UNCOMMON')
        self.assertEqual(props['tooltip']['quality'],'RARE')
        wand=service.item(7001)['item_properties']['variants']['tooltip']
        self.assertEqual(wand['weapon_damage']['dps'],29)
        self.assertEqual(wand['evidence_basis'],'classic_fallback')
        self.assertIsNone(wand['game_build'])
        self.assertEqual(wand['effects'][0]['text'],'Fixture effect')
        self.assertEqual(service.graph.search_items('Fixture')['total'],2)

    def test_character_tool_uses_saved_slots_and_base_stats_without_chat_bridge(self):
        self.adapter.import_file(self.db,self.addon)
        save=self.path/'AltsForever.lua'
        save.write_text('AltsForeverDB={v=2,chars={["Fixture"]={name="Fixture",class="WARLOCK",level=26,updated=1791371090,gear={[7]="|cnIQ3:|Hitem:6903::::::::26::::|h[Fixture Pants]|h|r",[13]=nil,[18]="|cnIQ3:|Hitem:7001::::::::26::::|h[Fixture Wand]|h|r"}}}}')
        AltsForeverAdapter().import_file(self.db,save)
        store=CharacterStore(self.db)
        snap=store.get(store.list()['characters'][0]['snapshot_id'])
        result=prepare_response('get_character_snapshot',snap)
        wand=next(i for i in result['items'] if i['item_id']==7001)
        self.assertEqual(wand['slot_name'],'Ranged')
        self.assertEqual(wand['equipped_name'],'Fixture Wand')
        self.assertEqual(wand['item_properties']['tooltip']['weapon_damage']['dps'],29)
        self.assertEqual(result['equipment_slots'][12]['status'],'recorded_empty')
        self.assertEqual(result['equipment_slots'][13]['status'],'not_recorded')
        self.assertEqual(result['character_stats']['status'],'not_recorded')
        self.assertEqual(wand['instance_stats_status'],'unresolved_bonus_and_enchant')
        self.assertNotIn('equipment_request',json.dumps(result))

    def test_failed_revision_preserves_last_valid_dataset_and_reactivation(self):
        self.adapter.import_file(self.db,self.addon)
        self.assertEqual(self.adapter.import_file(self.db,self.addon).records,0)
        original=(self.addon/'GearData.lua').read_text()
        self.write('GearData.lua',original+'os.execute("never execute")')
        with self.assertRaises(ValueError):self.adapter.import_file(self.db,self.addon)
        self.assertEqual(ResearchService(self.db,Settings()).item(6903)['item_properties']['variants']['gear']['stats']['spell_power'],12)
        self.write('GearData.lua',original.replace('sp=12','sp=13'))
        self.adapter.import_file(self.db,self.addon)
        self.write('GearData.lua',original)
        self.adapter.import_file(self.db,self.addon)
        self.assertEqual(ResearchService(self.db,Settings()).item(6903)['item_properties']['variants']['gear']['stats']['spell_power'],12)

    def test_duplicate_stats_are_preserved_without_adding_or_overwriting(self):
        raw,stats=stat_values('sta=14,shares=20,shares=10',TOOLTIP_STATS)
        self.assertEqual(raw['shares'],[20,10])
        self.assertNotIn('shadow_resistance',stats)
        self.assertEqual(stats['stamina'],14)

    def test_new_catalog_is_collected_by_existing_foreverguide_watcher(self):
        watcher=ForeverGuideWatcher(self.db,(str(self.addon),))
        with patch('goblin_eye.ingestion.discovery.discover_addon_paths',return_value=[self.addon]), \
             patch('goblin_eye.ingestion.foreverguide.discover_professiondb_paths',return_value=[]):
            results=watcher.scan_once()
        self.assertIn('foreverguide-items',[r.source_key for r in results])
        self.assertEqual(ResearchService(self.db,Settings()).item(6903)['item_properties']['status'],'recorded')


if __name__=='__main__':unittest.main()
