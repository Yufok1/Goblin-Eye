import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from goblin_eye.repository import Database
from goblin_eye.config import Settings
from goblin_eye.services import ResearchService
from goblin_eye.mcp_server import McpServer
from goblin_eye.characters import CharacterStore
from goblin_eye.item_instances import ItemInstances, normalize_stats
from goblin_eye.ingestion.alts_forever import AltsForeverAdapter
from goblin_eye.ingestion.questie_saved import QuestieSavedAdapter
from goblin_eye.ingestion.foreverguide_dungeons import ForeverGuideDungeonAdapter
from goblin_eye.ingestion.item_export_setup import install_item_export
from goblin_eye.agent_responses import prepare_response, size
from goblin_eye.ingestion.foreverguide_items import stat_values, TOOLTIP_STATS

ROOT=Path(__file__).resolve().parents[1]


def export_contract_fixture(addon, version='0.10.0'):
    manifest = '## Interface: 16001\n## Version: ' + version + '\nCore.lua\nGear.lua\nScanner.lua\nUpgrades.lua\n'
    (addon/'AltsForever.toc').write_text(manifest)
    files = {'Core.lua': 'local DB_VERSION = 2\nfunction ns.On(event, fn) end',
             'Gear.lua': 'function ns.ScanGear(c) end',
             'Scanner.lua': 'function ns.ScanContainers(bags, out, layout) end',
             'Upgrades.lua': 'function ns.ItemScore(link, role) end'}
    for name, text in files.items():
        (addon/name).write_text(text)
    return manifest


def lua(value):
    if isinstance(value,dict): return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in value.items())+'}'
    if isinstance(value,list): return lua(dict(enumerate(value,1)))
    if value is True: return 'true'
    if value is False: return 'false'
    if value is None: return 'nil'
    if isinstance(value,str): return json.dumps(value,ensure_ascii=False)
    return str(value)

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name); self.db=Database(self.path/'test.db'); self.db.migrate(ROOT/'migrations')
        self.save=self.path/'AltsForever.lua'
        self.key='item:6617:254:::::::26:::::1:12729'
        self.link='|cnIQ2:|H'+self.key+'|h[Fixture of Intellect]|h|r'
        self.record={'itemId':6617,'link':self.link,'capturedAt':1791371090,'build':'70170','locale':'enUS',
            'stats':{'ITEM_MOD_INTELLECT_SHORT':7},'tooltip':{1:'+7 Intellect',2:'Requires Level 24'}}
        self.char={'name':'Exact Name','class':'WARLOCK','faction':'Horde','level':26,'updated':1791371090,
            'gear':{7:self.link},'bags':{i:1 for i in range(10000,12000)},
            'goblinEyeGear':{'capturedAt':1791371090,'slots':{i:self.link if i==7 else False for i in range(1,20)}}}
        self.root={'v':2,'chars':{'Exact Name':self.char},'goblinEye':{'version':1,'items':{self.key:self.record}}}
        self.server=McpServer(ResearchService(self.db,Settings()))

    def import_save(self):
        self.save.write_text('AltsForeverDB='+lua(self.root),encoding='utf-8')
        return AltsForeverAdapter().import_file(self.db,self.save)

    def snapshot_id(self): return CharacterStore(self.db).list()['characters'][0]['snapshot_id']

    def test_exact_stats_paging_and_empty_slots_without_chat_bridge(self):
        self.import_save()
        snap=self.server._call('get_character_snapshot',{'snapshot_id':self.snapshot_id()})
        self.assertLess(size(snap),32000)
        self.assertEqual(len(snap['items']),1)
        item=snap['items'][0]
        self.assertEqual(item['instance_stats']['stats'],{'intellect':7})
        self.assertEqual(item['enchant_id'],254)
        self.assertEqual(snap['equipment_slots'][12]['status'],'recorded_empty')
        self.assertIn('character_sheet_capture_missing',snap['research_preflight']['blocking_reasons'])
        self.assertEqual(snap['inventory_summary']['record_counts_by_location']['bag'],2000)
        self.assertEqual(self.server._call('get_character_inventory',{'snapshot_id':self.snapshot_id(),'limit':10})['next_offset'],10)
        variants=self.server._call('get_item_variants',{'item_id':6617,'item_link':self.link})
        self.assertEqual(variants['records'][0]['tooltip'],['+7 Intellect','Requires Level 24'])
        self.assertNotIn('WoWAI',json.dumps(snap))

    def test_unequipped_variants_import_even_if_character_unchanged_and_builds_conflict(self):
        self.import_save()
        key=self.key.replace('12729','12730')
        self.root['goblinEye']['items'][key]={**self.record,'link':self.link.replace('12729','12730'),
            'stats':{'ITEM_MOD_STAMINA_SHORT':9}}
        result=self.import_save()
        self.assertEqual(result.snapshots,0)
        page=ItemInstances(self.db).page(6617)
        self.assertEqual(page['total'],2)
        self.assertEqual(ItemInstances(self.db).page(6617,item_link=self.link)['records'][0]['stats'],{'intellect':7})
        self.root['goblinEye']['items'][self.key]['build']='70205'
        self.import_save()
        self.assertEqual(CharacterStore(self.db).get(self.snapshot_id())['items'][0]['instance_stats_status'],'api_reported')

    def test_invalid_export_is_atomic(self):
        self.import_save()
        self.root['goblinEye']['items'][self.key]['stats']['ITEM_MOD_INTELLECT_SHORT']=True
        self.char['level']=27
        with self.assertRaises(ValueError): self.import_save()
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM character_snapshots').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM item_instance_facts').fetchone()[0],1)

    def capture_sheet(self):
        self.char['goblinEyeCharacter']={'version':1,'capturedAt':1791371090,'build':'70170','locale':'enUS',
            'race':'Orc','realm':'Fixture Realm','stats':{'max_health':900,'max_mana':1200,'strength':25,
                'agility':35,'stamina':45,'intellect':55,'spirit':65,'shadow_damage':43,'shadow_crit_percent':3.5},
            'talents':{'status':'recorded','configID':100,'nodes':[{'treeID':200,'nodeID':i,'rank':1,'spellID':600+i} for i in range(1,31)]},
            'buffs':{'status':'recorded','records':[{'spellID':700,'name':'Observed Buff','applications':1}]}}
        self.char['goblinEyeQuests']={'version':1,'capturedAt':1791371090,'completed':{843:True,846:True,849:True}}

    def test_character_sheet_talent_paging_and_client_quests(self):
        self.capture_sheet(); self.import_save()
        snap=self.server._call('get_character_snapshot',{'snapshot_id':self.snapshot_id(),'talent_limit':5,'talent_offset':10})
        self.assertEqual(snap['race'],'Orc'); self.assertEqual(snap['game_build'],'70170')
        self.assertEqual(snap['character_stats']['stats']['shadow_damage'],43)
        talents=snap['character_stats']['talents']
        self.assertEqual(talents['records'][0]['nodeID'],11); self.assertEqual(talents['next_offset'],15)
        self.assertNotIn('goblinEyeCharacter',snap['character'])
        self.assertEqual(snap['research_preflight']['audit_readiness'],'ready_for_source_qualified_comparison')
        quests=self.server._call('get_character_quests',{'snapshot_id':self.snapshot_id(),'limit':2})
        self.assertEqual([r['quest_id'] for r in quests['records']],[843,846])
        self.assertEqual(quests['source_key'],'local-alts-forever'); self.assertEqual(quests['next_offset'],2)
        self.char['goblinEyeCharacter']['stats']['shadow_damage']=True
        with self.assertRaises(ValueError): self.import_save()
        self.assertEqual(CharacterStore(self.db).get(self.snapshot_id())['character_stats']['stats']['shadow_damage'],43)

    def test_observed_item_metadata_survives_import_and_compact_snapshot(self):
        self.capture_sheet()
        self.record['metadata']={'name':'Observed Full-link Item','quality_id':2,'required_level':24,'item_level':29,'equip_location':'INVTYPE_LEGS'}
        self.import_save()
        snap=self.server._call('get_character_snapshot',{'snapshot_id':self.snapshot_id()})
        self.assertEqual(snap['items'][0]['observed_item_metadata']['required_level'],24)
        self.record['metadata']['required_level']=True
        with self.assertRaises(ValueError): self.import_save()

    def test_build_matched_observation_resolves_old_conflicts_without_guessing(self):
        self.capture_sheet(); self.import_save()
        self.root['goblinEye']['items'][self.key]['build']='70205'
        self.root['goblinEye']['items'][self.key]['stats']['ITEM_MOD_INTELLECT_SHORT']=99
        self.import_save()
        item=CharacterStore(self.db).get(self.snapshot_id())['items'][0]
        self.assertEqual(item['instance_stats']['stats']['intellect'],7)
        self.char['goblinEyeCharacter']['build']='70245'; self.import_save()
        snap=CharacterStore(self.db).get(self.snapshot_id())
        self.assertEqual(snap['items'][0]['instance_stats_status'],'different_observed_build')
        self.assertEqual(snap['research_preflight']['audit_readiness'],'blocked')
        self.assertEqual(snap['research_preflight']['blocking_slots'],['Legs'])

    def test_empty_client_completion_is_distinct_from_missing_capture(self):
        self.capture_sheet(); self.char['goblinEyeQuests']['completed']={}; self.import_save()
        page=CharacterStore(self.db).quests(self.snapshot_id())
        self.assertEqual(page['status'],'recorded'); self.assertEqual(page['total'],0)
        self.char['goblinEyeQuests']['completed']={843:1}
        with self.assertRaises(ValueError): self.import_save()

    def test_dynamic_recipe_plan_pattern_sources_skill_conflict_and_crafter(self):
        self.import_save()
        with self.db.transaction() as c:
            c.execute("INSERT INTO sources(source_key,name,source_type,trust_rank) VALUES ('fixture','Fixture','test',4)")
            source=c.execute('SELECT id FROM sources WHERE source_key=\'fixture\'').fetchone()[0]
            datasets=[]
            for revision in ('a','b'):
                datasets.append(c.execute("INSERT INTO research_datasets(source_id,dataset_key,sha256,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json) VALUES (?,?,?,'2026-10-07',0.5,'extracted','{}','[]')",(source,revision,revision)).lastrowid)
            fact=None
            for dataset,skill in zip(datasets,(120,130)):
                created=c.execute("INSERT INTO recipe_facts(dataset_id,spell_id,name,profession_id,profession,output_item_id,output_quantity,skill_required,attributes_json,raw_reference) VALUES (?,3100,'Fixture Craft',197,'Tailoring',3200,1,?,'{}','fixture')",(dataset,skill)).lastrowid
                fact=fact or created
                c.execute("INSERT INTO reagent_facts VALUES (?,3300,2)",(created,))
                c.execute("INSERT INTO recipe_teaching_items VALUES (?,3400,'fixture')",(created,))
            c.execute("INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference) VALUES (?,'npc',3500,'Fixture Pattern Mob','{\"min_level\":23,\"max_level\":25}','fixture')",(datasets[0],))
            c.execute("INSERT INTO acquisition_facts(dataset_id,item_id,method,entity_type,entity_id,probability,quest_condition,choice_reward,evidence_basis,raw_reference) VALUES (?,3400,'drop','npc',3500,NULL,0,0,'classic_baseline','fixture')",(datasets[0],))
        recipe=self.server._call('get_recipe_evidence',{'fact_id':fact,'snapshot_id':self.snapshot_id()})
        plan=recipe['learning_plan']
        self.assertTrue(plan['skill_conflict']); self.assertEqual(plan['learning_method'],'pattern')
        self.assertEqual(plan['pattern_sources'][0]['records'][0]['entity_name'],'Fixture Pattern Mob')
        self.assertEqual(plan['pattern_sources'][0]['records'][0]['evidence_basis'],'classic_baseline')
        self.assertEqual(plan['character']['crafter_status'],'needs_other_crafter_or_unrecorded_profession')
        with self.db.transaction() as c:
            c.execute('DELETE FROM recipe_teaching_items')
        plan=self.server._call('get_recipe_evidence',{'fact_id':fact})['learning_plan']
        self.assertEqual(plan['learning_method'],'unknown','absence of a pattern must not imply trainer access')

    def test_quest_completion_exact_namespace_and_persisted_freshness(self):
        self.import_save(); quests=self.path/'Questie.lua'
        def write(name):
            quests.write_text('QuestieConfig='+lua({'char':{name:{'complete':{i:True for i in range(1,169)}}}}))
        write('Exact'); QuestieSavedAdapter().import_file(self.db,quests)
        self.assertEqual(CharacterStore(self.db).quests(self.snapshot_id())['status'],'not_captured')
        write('Exact Name'); QuestieSavedAdapter().import_file(self.db,quests)
        old_snapshot=self.snapshot_id()
        self.assertEqual(CharacterStore(self.db).quests(old_snapshot)['status'],'not_captured')
        self.char['level']=27; self.import_save()
        page=self.server._call('get_character_quests',{'snapshot_id':self.snapshot_id(),'limit':100})
        self.assertEqual(page['total'],168); self.assertEqual(page['next_offset'],100)
        self.assertEqual(self.server._call('get_character_quests',{'snapshot_id':self.snapshot_id(),'offset':100})['records'][0]['quest_id'],101)
        first=page['file_saved_at']; stamp=quests.stat().st_mtime+60; os.utime(quests,(stamp,stamp))
        QuestieSavedAdapter().import_file(self.db,quests)
        self.assertEqual(CharacterStore(self.db).quests(self.snapshot_id())['file_saved_at'],first)
        self.char['level']=28; self.import_save()
        self.assertNotEqual(CharacterStore(self.db).quests(self.snapshot_id())['file_saved_at'],first)
        quests.write_text('QuestieConfig={char={["Exact Name"]={complete={[1]=1}}}}')
        with self.assertRaises(ValueError): QuestieSavedAdapter().import_file(self.db,quests)
        self.assertEqual(CharacterStore(self.db).quests(self.snapshot_id())['total'],168)

    def test_normalization_preserves_raw_and_never_calls_resistance_damage(self):
        raw,stats=stat_values('firres=10,frores=3,shares=5,atkpwr=12,hitrtng=2,critstrkrtng=1,armorbonus=7',TOOLTIP_STATS)
        self.assertEqual(stats['shadow_resistance'],5); self.assertNotIn('shadow_damage',stats)
        self.assertEqual(stats['hit_rating'],2); self.assertNotIn('spell_hit_rating',stats)
        self.assertEqual(raw['firres'],10)
        self.assertEqual(normalize_stats({'ITEM_MOD_POWER_REGEN0_SHORT':3,'ITEM_MOD_MANA_REGENERATION_SHORT':5}),{})

    def test_client_school_damage_survives_without_merging_spell_power(self):
        raw={'ITEM_MOD_'+school.upper()+'_DAMAGE_DONE_SHORT': i+10
             for i,school in enumerate(('holy','fire','nature','frost','shadow','arcane'))}
        raw.update({'ITEM_MOD_SPELL_POWER_SHORT':30,'ITEM_MOD_SPELL_DAMAGE_DONE_SHORT':20,
                    'RESISTANCE0_NAME':44,'RESISTANCE5_NAME':7})
        expected={school+'_damage':i+10
                  for i,school in enumerate(('holy','fire','nature','frost','shadow','arcane'))}
        expected.update({'spell_power':30,'spell_damage':20,'armor':44})
        before=raw.copy()
        self.assertEqual(normalize_stats(raw),expected)
        self.assertEqual(raw,before,'raw client evidence must remain unchanged')
        self.assertNotIn('shadow_resistance',normalize_stats(raw))

    def test_dungeon_filters_use_boss_membership_not_entrance_map(self):
        addon=self.path/'ForeverGuide'; addon.mkdir()
        files={'ForeverGuide.toc':'## Interface: 16001\n## Version: fixture\n',
            'DungeonLoot.lua':'-- foreverchanges.pro boss loot\nns.LOOT={bfd={{n="Old boss",id=100,items={{id=200,n="Old item"}}}}}',
            'DungeonData.lua':'-- QuestieDB (Forever) + foreverchanges.pro\nns.DUNGEONS={{key="bfd",en="Blackfathom Deeps",slug="blackfathom-deeps",map=1440},{key="rfk",en="Razorfen Kraul"},{key="rfd",en="Razorfen Downs"}}\nns.DQ={}',
            'Dungeons.lua':'rw and rw.fv','ItemSearch.lua':'fv = q.rw.fv'}
        for name,body in files.items(): (addon/name).write_text(body)
        ForeverGuideDungeonAdapter().import_file(self.db,addon)
        with self.db.transaction() as c:
            ds=c.execute('SELECT id FROM research_datasets').fetchone()[0]
            c.executemany('INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference) VALUES (?,\'npc\',?,?,?,?)',
                [(ds,101,'Entrance outsider','{"ui_map_id":1440}','outside')])
        page=self.server._call('search_world_entities',{'zone':'Blackfathom Deeps'})
        self.assertEqual([r['entity_id'] for r in page['records']],[100])
        self.assertIn('incomplete',page['dungeon_filter_scope'])
        with self.assertRaisesRegex(ValueError,'Ambiguous'): self.server._call('search_world_entities',{'dungeon':'Razorfen'})
        with self.db.transaction() as c:
            ds=c.execute('SELECT id FROM research_datasets').fetchone()[0]
            c.execute('UPDATE world_entity_facts SET attributes_json=? WHERE entity_id=100',
                (json.dumps({'spawns_by_area':{'1':[[1,2]]*10000}}),))
        entity=self.server._call('get_world_entity',{'entity_type':'npc','entity_id':100})
        self.assertLess(size(entity),32000)
        self.assertEqual(len(entity['assertions'][0]['attributes']['spawns_by_area_sample']['1']),2)

    def test_evidence_and_dataset_pages_do_not_skip_assertions(self):
        with self.db.transaction() as c:
            c.execute("INSERT INTO sources(source_key,name,source_type,trust_rank) VALUES ('fixture','Fixture','test',4)")
            source=c.execute('SELECT id FROM sources').fetchone()[0]
            for i in range(12):
                ds=c.execute("INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json) VALUES (?,?,?,'fixture','2026-10-07',0.5,'extracted',?, '[]')",
                    (source,str(i),str(i),json.dumps({'long':'x'*50000}))).lastrowid
                c.execute("INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference) VALUES (?,'npc',?,'Shadow Fixture','{}',?)",(ds,i+1,str(i)))
        names=[]; offset=0
        while True:
            page=self.server._call('search_evidence',{'query':'Shadow','limit':5,'offset':offset})
            names.extend(r['entity_id'] for r in page['records'])
            if page['next_offset'] is None: break
            offset=page['next_offset']
        self.assertEqual(sorted(names),list(range(1,13)))
        page=self.server._call('get_research_datasets',{'limit':5})
        self.assertEqual(page['total'],12); self.assertEqual(page['next_offset'],5)
        self.assertLess(size(page),32000); self.assertNotIn('manifest',page['records'][0])

    def test_installer_is_idempotent_backs_up_and_rejects_changed_contract(self):
        addon=self.path/'AltsForever'; addon.mkdir()
        export_contract_fixture(addon)
        helper=ROOT/'integrations/alts-forever/GoblinEyeExport.lua'; backup=self.path/'backups'
        self.assertTrue(install_item_export(addon,helper,backup))
        self.assertFalse(install_item_export(addon,helper,backup))
        self.assertEqual(len(list(backup.rglob('*.bak'))),1)
        self.assertEqual((addon/'AltsForever.toc').read_text().splitlines()[-1],'GoblinEyeExport.lua')
        (addon/'Gear.lua').write_text('changed')
        with self.assertRaises(ValueError): install_item_export(addon,helper,backup)

    def test_installer_repairs_edition_manifest_even_when_generic_is_installed(self):
        addon=self.path/'AltsForever'; addon.mkdir()
        original=export_contract_fixture(addon)
        (addon/'AltsForever.toc').write_text(original+'GoblinEyeExport.lua\n')
        (addon/'AltsForever_Camelot.toc').write_text(original)
        helper=ROOT/'integrations/alts-forever/GoblinEyeExport.lua';backup=self.path/'backups'
        (addon/'GoblinEyeExport.lua').write_bytes(helper.read_bytes())
        self.assertTrue(install_item_export(addon,helper,backup))
        self.assertFalse(install_item_export(addon,helper,backup))
        for name in ('AltsForever.toc','AltsForever_Camelot.toc'):
            self.assertEqual((addon/name).read_text().splitlines().count('GoblinEyeExport.lua'),1)
        self.assertTrue(any(p.name.startswith('AltsForever_Camelot.toc.') for p in backup.rglob('*.bak')))

    def test_unreviewed_edition_manifest_prevents_any_installation(self):
        addon=self.path/'AltsForever'; addon.mkdir()
        export_contract_fixture(addon)
        (addon/'AltsForever_Camelot.toc').write_text('## Interface: 16001\n## Version: changed\n')
        helper=ROOT/'integrations/alts-forever/GoblinEyeExport.lua'
        with self.assertRaisesRegex(ValueError,'AltsForever_Camelot.toc'):
            install_item_export(addon,helper,self.path/'backups')
        self.assertFalse((addon/'GoblinEyeExport.lua').exists())
        self.assertNotIn('GoblinEyeExport.lua',(addon/'AltsForever.toc').read_text())

    def test_reviewed_alts_releases_install_into_both_manifests(self):
        for version in ('0.13.0', '0.16.0', '1.0.1'):
            with self.subTest(version=version):
                addon=self.path/version; addon.mkdir()
                manifest=export_contract_fixture(addon, version)
                (addon/'AltsForever_Camelot.toc').write_text(manifest)
                helper=ROOT/'integrations/alts-forever/GoblinEyeExport.lua'
                self.assertTrue(install_item_export(addon,helper,self.path/'backups'))
                self.assertFalse(install_item_export(addon,helper,self.path/'backups'))
                for name in ('AltsForever.toc', 'AltsForever_Camelot.toc'):
                    self.assertEqual((addon/name).read_text().splitlines()[-1], 'GoblinEyeExport.lua')

    def test_current_release_rejects_changed_schema_signatures_and_mixed_manifests(self):
        cases = (('Core.lua', 'local DB_VERSION = 3\nfunction ns.On(event, fn) end'),
                 ('Gear.lua', 'function ns.ScanGear(c, mode) end'),
                 ('AltsForever_Camelot.toc', '## Interface: 16001\n## Version: 0.13.0\nCore.lua\nGear.lua\nScanner.lua\nUpgrades.lua\n'),
                 ('AltsForever_Camelot.toc', '## Interface: 16001\n## Version: 99.0.0\n'),
                 ('AltsForever_Camelot.toc', '## Interface: 16001\n## Version: 0.16.0\nCore.lua\n'))
        for index, (name, text) in enumerate(cases):
            with self.subTest(name=name, text=text):
                addon=self.path/str(index); addon.mkdir()
                export_contract_fixture(addon, '0.16.0')
                (addon/name).write_text(text)
                with self.assertRaises(ValueError):
                    install_item_export(addon,ROOT/'integrations/alts-forever/GoblinEyeExport.lua',self.path/'backups')
                self.assertFalse((addon/'GoblinEyeExport.lua').exists())
                self.assertFalse((self.path/'backups').exists())
                self.assertNotIn('GoblinEyeExport.lua', (addon/'AltsForever.toc').read_text())

    def test_personal_reset_erases_new_observations(self):
        self.import_save()
        from goblin_eye.auction_policy import reset_personal_data
        reset_personal_data(self.db)
        with self.db.transaction() as c:
            for table in ('character_snapshots','item_instance_facts','character_quest_snapshots'):
                self.assertEqual(c.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

if __name__=='__main__': unittest.main()
