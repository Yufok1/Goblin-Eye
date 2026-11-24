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

snap = server._call('get_character_snapshot', {'snapshot_id': 88})
print("Saved location:", snap.get('saved_location'))
print("Character stats:", snap.get('character_stats'))
print("Equipped items total:", len(snap.get('equipment_slots', [])))
for s in snap.get('equipment_slots', []):
    print(f"Slot {s.get('slot_id')} ({s.get('slot_name')}): {s.get('equipped_name')} (id: {s.get('item_id')}) link: {s.get('item_link')}")

print("\nInventory items lookup:")
inv = server._call('get_character_inventory', {'snapshot_id': 88})
for r in inv.get('records', []):
    item_id = r['item_id']
    info = server._call('get_item_research', {'item_id': item_id})
    # print keys of info
    name = info.get('name') or info.get('item_name')
    if not name and 'item' in info:
        name = info['item'].get('name')
    if not name and 'catalog' in info:
        name = info['catalog'].get('name')
    print(f"Item {item_id}: qty {r.get('quantity')}, name='{name}', info_keys={list(info.keys()) if isinstance(info, dict) else 'none'}")
    if not name and isinstance(info, dict):
        print(f"   details: {str(info)[:200]}")
