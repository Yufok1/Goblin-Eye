"""Read Questie's existing personal completion cache, without evaluating Lua."""
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from .alts_forever import AltsForeverWatcher
from .base import ImportResult
from .bounded import read_file
from .discovery import discover_saved_files
from .lua_literals import LuaLiteralReader

SOURCE_KEY='local-questie'

class QuestieSavedAdapter:
    def import_file(self,database,path):
        path=Path(path).resolve()
        text=read_file(path,16*1024*1024).decode('utf-8-sig')
        reader=LuaLiteralReader(text)
        globals={}
        while True:
            reader.skip()
            if reader.position==len(text): break
            match=re.match(r'[A-Za-z_][A-Za-z0-9_]*',text[reader.position:])
            if not match: raise ValueError('Unexpected Questie saved expression')
            name=match[0]; reader.position+=len(name); reader.expect('=')
            if name not in ('QuestieConfig','QuestieProfilerEnabled') or name in globals:
                raise ValueError('Unreviewed Questie saved global')
            globals[name]=reader.read()
        root=globals.get('QuestieConfig')
        if not isinstance(root,dict) or not isinstance(root.get('char'),dict):
            raise ValueError('Missing Questie character cache')
        saved=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()
        records=[]
        for name,char in root['char'].items():
            if not isinstance(name,str) or not isinstance(char,dict): raise ValueError('Invalid Questie character')
            if 'complete' not in char: continue
            complete=char['complete']
            if not isinstance(complete,dict) or len(complete)>100000: raise ValueError('Invalid completion cache')
            if any(type(k) is not int or k<=0 or type(v) is not bool for k,v in complete.items()):
                raise ValueError('Invalid completed quest entry')
            body=json.dumps({'completed':sorted(k for k,v in complete.items() if v)},sort_keys=True)
            records.append((name,body,hashlib.sha256((body+saved).encode()).hexdigest()))
        # Match Alts' exact account/file namespace, never a partial character name.
        namespace=hashlib.sha256(str(path.with_name('AltsForever.lua')).casefold().encode()).hexdigest()[:24]
        now=datetime.now(timezone.utc).isoformat()
        with database.write_transaction() as c:
            c.execute('''INSERT INTO sources(source_key,name,source_type,trust_rank,last_success_at)
                VALUES (?,'Questie saved quest completion','local_character_observation',1,?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL''',(SOURCE_KEY,now))
            count=0
            for name,body,digest in records:
                count+=c.execute('''INSERT OR IGNORE INTO character_quest_snapshots
                    (namespace,character_name,imported_at,file_saved_at,sha256,payload_json,raw_reference)
                    VALUES (?,?,?,?,?,?,?)''',(namespace,name,now,saved,digest,body,
                    path.as_uri()+'#QuestieConfig/char/'+name+'/complete')).rowcount
        return ImportResult('questie_saved_completion_v1',SOURCE_KEY,count,0,
            ('Exact account and full-name matching only. Save-file time is not quest completion time; absence does not establish eligibility.',))

class QuestieSavedWatcher(AltsForeverWatcher):
    def scan_once(self):
        results=[]
        for path in discover_saved_files('Questie.lua',self.paths):
            try:
                stat=path.stat(); signature=(stat.st_mtime_ns,stat.st_size)
                if self._signatures.get(str(path))==signature: continue
                results.append(QuestieSavedAdapter().import_file(self.database,path))
                self._signatures[str(path)]=signature
            except Exception as error:
                logging.exception('Questie saved import failed: %s',path)
                with self.database.write_transaction() as c:
                    c.execute('''INSERT INTO sources(source_key,name,source_type,trust_rank,last_error)
                        VALUES (?,'Questie saved quest completion','local_character_observation',1,?)
                        ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error''',(SOURCE_KEY,str(error)))
        return results
