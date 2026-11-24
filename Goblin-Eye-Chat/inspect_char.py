import json
from pathlib import Path
from goblin_eye.config import Settings
from goblin_eye.repository.database import Database
from goblin_eye.services import ResearchService
from goblin_eye.mcp_server import McpServer

cfg = Settings.load(Path('D:/End-Game/ended_game/codex_playground/Goblin-Eye/config.json'))
db = Database(cfg.database_path)
svc = ResearchService(db, cfg)
server = McpServer(svc)

with open('af0bd89b_char_data.json') as f:
    d = json.load(f)

print('=== ALL INVENTORY ITEMS WITH NAMES ===')
for r in d['inventory_items']['records']:
    item_id = r['item_id']
    item_info = server._call('get_item_research', {'item_id': item_id})
    name = item_info.get('catalog', {}).get('name') if isinstance(item_info, dict) else None
    print(f"ID {item_id}: count {r.get('quantity')}, name: {name}")

print('\n=== ALL EQUIPPED ITEMS ===')
for r in d['equipment']['records']:
    print(f"Slot {r.get('slot_id')} ({r.get('slot_name')}): {r.get('equipped_name')} (ID: {r.get('item_id')})")

print('\n=== ALL ACTIVE QUESTS ===')
for r in d['active_quests']['records']:
    print(f"Quest {r.get('quest_id')}: {r.get('title')}")

print('\n=== FULL SNAPSHOT KEYS ===')
snap = server._call('get_character_snapshot', {'snapshot_id': 88})
print("Snapshot keys:", list(snap.keys()))
if 'professions' in snap:
    print("Professions:", snap['professions'])
if 'skills' in snap:
    print("Skills:", snap['skills'])
