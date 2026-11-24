from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest
from unittest.mock import patch

from goblin_eye.repository import Database
from goblin_eye.config import Settings
from goblin_eye.services import ResearchService
from goblin_eye.history import public_capture, MarketHistory
from goblin_eye.characters import CharacterStore
from goblin_eye.ingestion.alts_forever import AltsForeverAdapter
from goblin_eye.ingestion.questie_saved import QuestieSavedAdapter
from goblin_eye.ingestion.auctionator import select_auctionator_markets

ROOT=Path(__file__).resolve().parents[1]


class DiagnosticRepairTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.db=Database(self.root/'test.db');self.db.migrate(ROOT/'migrations')

    def market(self,c,key,source):
        c.execute("INSERT OR IGNORE INTO sources(source_key,name,source_type,trust_rank) VALUES (?,?, 'test',4)",(source,source))
        source_id=c.execute('SELECT id FROM sources WHERE source_key=?',(source,)).fetchone()[0]
        market_id=c.execute("INSERT INTO markets(market_key,name,region,ruleset,faction,is_verified,source_id,retrieved_at,confidence,evidence_kind) VALUES (?,?,'unknown','unknown','unknown',0,?,?,0.9,'observed')",(key,key,source_id,datetime.now(timezone.utc).isoformat())).lastrowid
        return source_id,market_id

    def test_regional_bucket_uses_explicit_profile_without_inventing_realm(self):
        profile=dict(realm='unknown',faction='horde',ruleset='pvp',region='unknown')
        selected,skipped=select_auctionator_markets({'PvP':{}},profile)
        self.assertEqual(selected['PvP'][:2],('unknown','unknown'))
        self.assertEqual(profile['realm'],'unknown');self.assertEqual(skipped,[])
        with self.assertRaises(ValueError):select_auctionator_markets({'PvP':{}},{**profile,'faction':'unknown'})

    def test_fresh_public_capture_never_makes_empty_local_market_fresh(self):
        now=datetime.now(timezone.utc)
        with self.db.write_transaction() as c:
            source,market=self.market(c,'forever.pvp.horde.us','ahledger')
            body=('AHL1|forever/pvp/horde/us|'+str(int(now.timestamp()))+'|1\n101:20:18:2:22:21:18:25\n').encode()
            public_capture(c,source,market,None,body,now.isoformat(),period='forever-live')
        with patch('goblin_eye.ingestion.discovery.WOW_ROOTS',()):
            health=ResearchService(self.db,Settings(database_path=str(self.db.path))).sources()
        self.assertTrue(health['is_stale']);self.assertIsNone(health['newest_snapshot'])
        self.assertFalse(health['selected_market_has_prices'])
        self.assertEqual(health['freshness']['public_references'][0]['status'],'recent')
        self.assertEqual(health['freshness']['local_prices'][0]['status'],'missing')

    def test_public_import_label_cannot_assert_observation_phase(self):
        with self.db.write_transaction() as c:
            source,market=self.market(c,'forever.pvp.horde.us','ahledger')
            body=b'AHL1|forever/pvp/horde/us|1791374689|1\n101:20:18:2:22:21:18:25\n'
            public_capture(c,source,market,None,body,'2026-11-05T00:00:00+00:00',period='forever-live')
            row=c.execute('SELECT economic_period,import_economic_period FROM market_captures').fetchone()
        self.assertEqual(tuple(row),('unknown','forever-live'))
        history=MarketHistory(self.db)
        with self.assertRaises(ValueError):history.points(101,'forever.pvp.horde.us',period='forever-live')
        point=history.points(101,'forever.pvp.horde.us')['records'][0]
        self.assertEqual(point['import_economic_period'],'forever-live');self.assertTrue(point['observed_at'].startswith('2026-10-'))

    def test_freshness_counts_priced_captures_once_and_excludes_empty_newer_captures(self):
        from goblin_eye.history import record_capture
        from goblin_eye.freshness import evidence_freshness
        with self.db.write_transaction() as c:
            source,market=self.market(c,'forever.pvp.horde.us','ahledger')
            for identity,observed,points in (
                ('priced','2026-11-15T10:00:00+00:00',[
                    dict(item_key='101',observed_date='2026-11-15',minimum_copper=0),
                    dict(item_key='102',observed_date='2026-11-16',median_copper=50)]),
                ('empty','2026-11-18T10:00:00+00:00',[]),
                ('unpriced','2026-11-18T11:00:00+00:00',[
                    dict(item_key='103',observed_date='2026-11-18')])):
                record_capture(c,source,market,identity,observed,observed,'source_table',points)
        with self.db.transaction() as c:
            traced=[];c.set_trace_callback(traced.append)
            result=evidence_freshness(c,'wow-forever',24)
            plan=[r['detail'] for r in c.execute('EXPLAIN QUERY PLAN '+traced[0])]
        public=result['public_references'][0]
        self.assertEqual(public['evidence_count'],1)
        self.assertEqual(public['observed_at'],'2026-11-15T10:00:00+00:00')
        self.assertEqual(public['observed_date'],'2026-11-16')
        self.assertFalse(any(p['has_evidence'] for p in result['local_prices']))
        self.assertTrue(any('idx_priced_capture_date' in detail for detail in plan),plan)
        self.assertFalse(any('SCAN p' == detail for detail in plan),plan)

    def test_item_search_keeps_unnamed_ids_literal_names_and_pagination(self):
        from goblin_eye.item_graph import ItemGraph
        with self.db.write_transaction() as c:
            source,market=self.market(c,'wow-forever','local-auctionator')
            # Price-only identity has no catalog/name assertion.
            c.execute("""INSERT INTO price_observations(source_id,market_id,item_key,item_id,
                scan_day,observed_date,imported_at,source_modified_at,confidence,evidence_kind)
                VALUES (?,?,'99123',99123,1,'2026-11-18','2026-11-18','2026-11-18',1,'observed')""",(source,market))
            dataset=c.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,retrieved_at,
                confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?,'fixture','fixture','2026-11-18',1,'extracted','{}','[]')""",(source,)).lastrowid
            c.executemany("""INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference)
                VALUES (?,'item',?,?,'{}','fixture')""",[(dataset,10,'Literal_100%'),(dataset,11,'Literal_100% two'),(dataset,12,'LiteralX1000')])
        graph=ItemGraph(self.db)
        self.assertEqual(graph.search_items('99123')['items'],[dict(item_id=99123,name=None)])
        first=graph.search_items('Literal_100%',limit=1)
        second=graph.search_items('Literal_100%',limit=1,offset=1)
        self.assertEqual(first['total'],2);self.assertEqual(first['items'][0]['item_id'],10)
        self.assertEqual(second['items'][0]['item_id'],11)
        self.assertEqual(graph.search_items('99123'+'0'*20)['total'],0)
        self.assertEqual(graph.search_items('')['total'],4)

    def test_quest_cutoff_explains_later_cache_without_exposing_its_ids(self):
        save=self.root/'AltsForever.lua'
        save.write_text('AltsForeverDB={v=2,chars={["Fixture Name"]={name="Fixture Name",class="WARLOCK",level=1,updated=1791374689}}}')
        AltsForeverAdapter().import_file(self.db,save)
        with self.db.transaction() as c:old=c.execute('SELECT MAX(id) FROM character_snapshots').fetchone()[0]
        quest=self.root/'Questie.lua';quest.write_text('QuestieConfig={char={["Fixture Name"]={complete={[101]=true}}}}')
        QuestieSavedAdapter().import_file(self.db,quest)
        before=CharacterStore(self.db).quests(old)
        self.assertEqual(before['exclusion_reason'],'imported_after_snapshot');self.assertEqual(before['records'],[])
        save.write_text(save.read_text().replace('level=1','level=2'));AltsForeverAdapter().import_file(self.db,save)
        with self.db.transaction() as c:new=c.execute('SELECT MAX(id) FROM character_snapshots').fetchone()[0]
        self.assertEqual(CharacterStore(self.db).quests(new)['records'][0]['quest_id'],101)
        self.assertEqual(CharacterStore(self.db).quests(old)['records'],[])

    def test_upgrade_preserves_import_period_and_historical_capture_dates(self):
        legacy=Database(self.root/'legacy.db');migrations=self.root/'migrations';migrations.mkdir()
        for p in (ROOT/'migrations').glob('*.sql'):
            if p.name<'024':shutil.copyfile(p,migrations/p.name)
        legacy.migrate(migrations)
        with legacy.write_transaction() as c:
            source,market=self.market(c,'forever.pvp.horde.us','ahledger')
            c.execute("INSERT INTO market_captures(source_id,market_id,identity,observed_at,retrieved_at,granularity,economic_period,limitations_json) VALUES (?,?,'old','2026-10-01T00:00:00+00:00','2026-11-05T00:00:00+00:00','source_table','forever-live','[]')",(source,market))
        legacy.migrate(ROOT/'migrations')
        with legacy.transaction() as c:row=c.execute('SELECT * FROM market_captures').fetchone()
        self.assertEqual(row['economic_period'],'unknown');self.assertEqual(row['import_economic_period'],'forever-live')
        self.assertEqual(row['observed_at'],'2026-10-01T00:00:00+00:00')


if __name__=='__main__':unittest.main()
