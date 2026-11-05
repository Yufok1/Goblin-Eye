import base64
import json
import struct
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory

from goblin_eye.ingestion.questiedb import QuestieDbAdapter, AREA_MAP_FILE
from goblin_eye.repository import Database
from goblin_eye.research_queries import ResearchQueries

ROOT = Path(__file__).resolve().parents[1]


def cbor(value):
    def head(kind, n):
        if n < 24: return bytes([kind * 32 + n])
        if n < 256: return bytes([kind * 32 + 24, n])
        return bytes([kind * 32 + 25]) + struct.pack('>H', n)
    if isinstance(value, int): return head(0, value) if value >= 0 else head(1, -1-value)
    if isinstance(value, str):
        body=value.encode(); return head(3,len(body))+body
    if isinstance(value, list): return head(4,len(value))+b''.join(map(cbor,value))
    if isinstance(value, dict): return head(5,len(value))+b''.join(cbor(k)+cbor(v) for k,v in value.items())
    raise ValueError(value)


class QuestImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.db=Database(self.root/'test.db'); self.db.migrate(ROOT/'migrations')
        mapping=self.root/AREA_MAP_FILE; mapping.parent.mkdir(parents=True)
        mapping.write_text('ZoneDB.private.areaIdToUiMapId = [[return { [400] = 1441, [406] = 1442, }]]')
        self.rows={'Npc-IDS':[], 'Object-IDS':[10], 'Quest-IDS':[20,21],
            'Object-10-S':{1:'Fixture herb',5:400,'p':8}, 'Object-10-4':{400:[[20,30]],406:[[40,50]]},
            'Quest-20-S':{1:'Fixture quest',4:18,5:29,17:400,'p':2}, 'Quest-20-2':{1:[100]},
            'Quest-21-S':{1:'Class quest',4:20,5:30,17:-61}}
        self.write()

    def write(self):
        lines=['## Interface: 16001','## X-Flavor: Forever','## X-Mode: baked','## Version: fixture']
        for key,value in self.rows.items():
            body=cbor(value); body=zlib.compress(body) if key.endswith('-IDS') else body
            lines.append('## X-'+key+': '+base64.b64encode(body).decode())
        lines.extend('## Padding-'+str(i)+': value' for i in range(100))
        (self.root/'QuestieDB_Forever.toc').write_text('\n'.join(lines))

    def test_quest_fields_zone_level_and_multizone_object_queries(self):
        QuestieDbAdapter().import_file(self.db,self.root)
        q=ResearchQueries(self.db)
        result=q.world(entity_type='quest',zone='Thousand Needles',min_level=27,max_level=31)
        self.assertEqual(result['total'],1)
        attrs=result['records'][0]['attributes']
        self.assertEqual(attrs['required_level'],18)
        self.assertEqual(attrs['quest_fields']['startedBy'],{'1':[100]})
        self.assertEqual(attrs['area_id'],400)
        self.assertEqual(q.world(entity_type='quest',zone='Thousand Needles',max_level=20)['total'],0)
        self.assertEqual(q.world(entity_type='object',zone='Stonetalon')['total'],1)
        self.assertEqual(q.world(entity_type='object',ui_map_id=1442)['total'],1)
        self.assertEqual(q.world(entity_type='object',query='Stonetalon')['total'],1)
        self.assertEqual(q.world(entity_type='quest',query='Class quest')['records'][0]['attributes']['zone_or_sort'],-61)
        QuestieDbAdapter().import_file(self.db,self.root)
        self.assertEqual(q.world(entity_type='quest')['total'],2)

    def test_upgrade_keeps_old_evidence_and_failed_import_keeps_active_data(self):
        adapter=QuestieDbAdapter();adapter.import_file(self.db,self.root)
        self.rows['Quest-20-S'][1]='Changed title';self.write();adapter.import_file(self.db,self.root)
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM research_datasets').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT sum(active) FROM research_datasets').fetchone()[0],1)
        del self.rows['Quest-20-2'];self.write()
        with self.assertRaises(ValueError): adapter.import_file(self.db,self.root)
        self.assertEqual(ResearchQueries(self.db).world(entity_type='quest',query='Changed title')['total'],1)

if __name__=='__main__': unittest.main()
