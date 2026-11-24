import sqlite3
import json

db_path = r'D:\End-Game\ended_game\codex_playground\Goblin-Eye\data\forever-live\goblin-eye.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

ids = [6624, 16189, 20558, 270030]
print("--- UNKNOWN IDS CHECK ---")
for i in ids:
    cur.execute("SELECT attributes_json FROM item_property_facts WHERE item_id = ?", (i,))
    r = cur.fetchone()
    if r:
        print(f"ID {i} in item_property_facts: {r[0][:200]}")
    else:
        print(f"ID {i}: NOT in item_property_facts")

print("\n--- CHARACTER QUEST SNAPSHOTS ---")
cur.execute("SELECT id, namespace, character_name, file_saved_at, payload_json FROM character_quest_snapshots WHERE character_name LIKE '%Hair%'")
rows = cur.fetchall()
for r in rows:
    print(f"ID {r[0]}, namespace {r[1]}, char {r[2]}, saved {r[3]}")
    data = json.loads(r[4])
    print("Keys in payload:", list(data.keys()))
    if 'active_quests' in data:
        for q in data['active_quests']:
            print(f"  Active Quest {q.get('id') or q.get('quest_id')}: {q.get('title')} | Obj: {q.get('objectives')}")
    elif 'quests' in data:
        print("Quests sample:", str(data['quests'])[:300])
    elif isinstance(data, list):
        print("List length:", len(data))
        for q in data[:10]:
            print("  ", q)
    elif 'log' in data:
        for q in data['log']:
            print(f"  Log: {q}")
