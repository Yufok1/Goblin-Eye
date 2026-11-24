import copy
import unittest
from unittest.mock import patch

import test_research_coverage as coverage
from goblin_eye.agent_responses import size
from goblin_eye.characters import CharacterStore


class ActiveQuestTests(unittest.TestCase):
    setUp = coverage.CoverageTests.setUp
    import_save = coverage.CoverageTests.import_save
    snapshot_id = coverage.CoverageTests.snapshot_id

    def capture(self):
        self.char['goblinEyeQuestLog']={'version':1,'capturedAt':1791371190,'build':'70938',
            'status':'recorded','reportedQuestCount':3,'entries':[
                {'questID':i,'title':f'Quest {i}','readyForTurnIn':i==3,
                 'objectives':{'status':'recorded','records':[
                     {'index':1,'text':'Things: 2/5','numFulfilled':2,'numRequired':5,'finished':False}]}}
                for i in range(1,4)]}
        self.char['goblinEyeLocation']={'version':1,'capturedAt':1791371180,'build':'70938',
            'status':'recorded','zone':'Fixture zone','subZone':'Landmark','uiMapID':123,'x':0.42,'y':0.63}

    def test_saved_log_pagination_location_and_history(self):
        self.capture(); self.import_save(); old=self.snapshot_id()
        page=self.server._call('get_character_active_quests',{'snapshot_id':old,'limit':2})
        self.assertEqual(page['next_offset'],2)
        self.assertFalse(page['records'][0]['ready_for_turn_in'])
        self.assertEqual(page['records'][0]['objectives'][0]['fulfilled'],2)
        self.assertEqual(page['saved_location']['x'],0.42)
        self.assertNotEqual(page['captured_at'],page['saved_location']['captured_at'])
        self.assertNotEqual(page['captured_at'],page['imported_at'])
        last=self.server._call('get_character_active_quests',{'snapshot_id':old,'offset':2})
        self.assertTrue(last['records'][0]['ready_for_turn_in'])
        self.assertIsNone(last['next_offset'])
        snap=self.server._call('get_character_snapshot',{'snapshot_id':old})
        self.assertEqual(snap['active_quest_log']['total'],3)
        self.assertNotIn('goblinEyeQuestLog',snap['character'])
        self.assertEqual(snap['saved_location']['subzone'],'Landmark')
        self.char['goblinEyeQuestLog']['entries']=[]
        self.char['goblinEyeQuestLog']['reportedQuestCount']=0
        self.import_save()
        self.assertEqual(CharacterStore(self.db).active_quests(old)['total'],3)
        self.assertEqual(CharacterStore(self.db).active_quests(self.snapshot_id())['total'],0)

    def test_missing_empty_partial_are_distinct(self):
        self.import_save()
        self.assertEqual(CharacterStore(self.db).active_quests(self.snapshot_id())['status'],'not_captured')
        self.capture()
        log=self.char['goblinEyeQuestLog']; log['status']='partial'
        del log['entries'][0]['readyForTurnIn']
        self.import_save()
        page=CharacterStore(self.db).active_quests(self.snapshot_id())
        self.assertIsNone(page['records'][0]['ready_for_turn_in'])
        self.assertEqual(page['status'],'partial')
        log.update(status='recorded',entries=[],reportedQuestCount=0)
        self.import_save()
        page=CharacterStore(self.db).active_quests(self.snapshot_id())
        self.assertEqual((page['status'],page['total']),('recorded',0))

    def test_invalid_observations_are_atomic(self):
        self.capture(); self.import_save(); old=self.snapshot_id()
        original=copy.deepcopy(self.char)
        mutations=[lambda c:c['goblinEyeLocation'].update(x=1.2),
            lambda c:c['goblinEyeLocation'].update(y=None),
            lambda c:c['goblinEyeQuestLog']['entries'][0].update(readyForTurnIn=1),
            lambda c:c['goblinEyeQuestLog']['entries'][1].update(questID=1),
            lambda c:c['goblinEyeQuestLog'].update(reportedQuestCount=0)]
        for change in mutations:
            self.char.clear(); self.char.update(copy.deepcopy(original)); change(self.char)
            with self.assertRaises(ValueError): self.import_save()
            self.assertEqual(self.snapshot_id(),old)

    def test_source_health_remains_bounded_and_pageable(self):
        raw=self.server.service.sources()
        raw['markets']=[{'market_key':f'fixture-{i}','name':'Long source label '*20} for i in range(100)]
        raw['freshness']['public_references']=[{'market_key':f'fixture-{i}','observed_at':'unknown'} for i in range(100)]
        with patch.object(self.server.service,'sources',return_value=copy.deepcopy(raw)):
            summary=self.server._call('get_source_health',{})
            self.assertLess(size(summary),32000)
            self.assertEqual(summary['section_counts']['markets'],100)
        with patch.object(self.server.service,'sources',return_value=copy.deepcopy(raw)):
            page=self.server._call('get_source_health',{'section':'markets','offset':20,'limit':10})
            self.assertEqual(page['records'][0]['market_key'],'fixture-20')
            self.assertEqual(page['next_offset'],30)


if __name__=='__main__': unittest.main()
