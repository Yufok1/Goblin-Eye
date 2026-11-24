import sqlite3
import json

db_path = r'D:\End-Game\ended_game\codex_playground\Goblin-Eye\data\forever-live\goblin-eye.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

inv_ids = [1180, 1210, 3174, 5058, 5165, 5511, 6624, 6915, 6948, 16189, 16746, 20558, 248682, 248683, 248685, 248702, 250187]
print("--- INVENTORY ITEMS ---")
for item_id in inv_ids:
    cur.execute("SELECT id, name, quality, item_class, subclass, required_level FROM items WHERE id = ?", (item_id,))
    row = cur.fetchone()
    if row:
        print(f"ID {item_id}: {row}")
    else:
        cur.execute("SELECT item_id, item_properties FROM item_property_facts WHERE item_id = ?", (item_id,))
        p_row = cur.fetchone()
        name = json.loads(p_row[1]).get('catalog', {}).get('name') if p_row and p_row[1] else None
        print(f"ID {item_id} (not in items): name={name}")

equip_ids = [281265, 10657, 14133, 2911, 6568, 14374, 3647, 270030, 6414, 11982, 12979, 273637, 5323, 8186]
print("\n--- EQUIPPED ITEMS ---")
for item_id in equip_ids:
    cur.execute("SELECT id, name, quality, item_class, subclass, required_level FROM items WHERE id = ?", (item_id,))
    row = cur.fetchone()
    if row:
        print(f"ID {item_id}: {row}")
    else:
        cur.execute("SELECT item_id, item_properties FROM item_property_facts WHERE item_id = ?", (item_id,))
        p_row = cur.fetchone()
        name = json.loads(p_row[1]).get('catalog', {}).get('name') if p_row and p_row[1] else None
        print(f"ID {item_id} (not in items): name={name}")

print("\n--- CHARACTER INVENTORY FROM DB (snapshot 88) ---")
cur.execute("SELECT snapshot_id, location, item_id, quantity, raw_link FROM character_inventory_observations WHERE snapshot_id = 88")
for r in cur.fetchall():
    print(r)

print("\n--- CHARACTER ITEM OBSERVATIONS (EQUIPPED) ---")
cur.execute("SELECT slot_id, slot_name, item_id, item_name, item_link FROM character_item_observations WHERE snapshot_id = 88")
for r in cur.fetchall():
    print(r)
