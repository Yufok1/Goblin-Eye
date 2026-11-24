import sqlite3
import json

db_path = r'D:\End-Game\ended_game\codex_playground\Goblin-Eye\data\forever-live\goblin-eye.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

inv_ids = [1180, 1210, 3174, 5058, 5165, 5511, 6624, 6915, 6948, 16189, 16746, 20558, 248682, 248683, 248685, 248702, 250187]

def get_item_info(item_id):
    cur.execute("SELECT id, name, quality, item_class, subclass, required_level FROM items WHERE id = ?", (item_id,))
    row = cur.fetchone()
    if row:
        return {'id': row[0], 'name': row[1], 'quality': row[2], 'class': row[3], 'subclass': row[4], 'req_level': row[5]}
    cur.execute("SELECT attributes_json FROM item_property_facts WHERE item_id = ?", (item_id,))
    p_row = cur.fetchone()
    if p_row:
        data = json.loads(p_row[0])
        catalog = data.get('catalog', {})
        return {'id': item_id, 'name': catalog.get('name'), 'quality': catalog.get('quality'), 'class': catalog.get('item_class_id'), 'subclass': catalog.get('item_subclass_id'), 'req_level': catalog.get('required_level')}
    return {'id': item_id, 'name': 'Unknown'}

print("=== INVENTORY ITEMS ===")
for i in inv_ids:
    cur.execute("SELECT quantity FROM character_inventory_observations WHERE snapshot_id = 88 AND item_id = ?", (i,))
    qty_row = cur.fetchone()
    qty = qty_row[0] if qty_row else 1
    info = get_item_info(i)
    print(f"ID {i}: qty {qty} | {info.get('name')} | Quality: {info.get('quality')} | Class: {info.get('class')}/{info.get('subclass')} | ReqLvl: {info.get('req_level')}")

equip_ids = [281265, 10657, 14133, 2911, 6568, 14374, 3647, 270030, 6414, 11982, 12979, 273637, 5323, 8186]
print("\n=== EQUIPPED ITEMS ===")
cur.execute("SELECT slot_id, item_id FROM character_item_observations WHERE snapshot_id = 88")
for slot_id, item_id in cur.fetchall():
    info = get_item_info(item_id)
    print(f"Slot {slot_id}: {info.get('name')} (ID: {item_id})")

print("\n=== REAGENT USES FOR INVENTORY ITEMS ===")
for i in inv_ids:
    # check recipe_reagents
    cur.execute("SELECT r.id, r.name, r.profession, r.skill_required FROM recipe_reagents rr JOIN recipes r ON rr.recipe_id = r.id WHERE rr.item_id = ?", (i,))
    recs = cur.fetchall()
    # also check reagent_facts
    cur.execute("SELECT rf.recipe_fact_id FROM reagent_facts rf WHERE rf.item_id = ?", (i,))
    rf_recs = cur.fetchall()
    info = get_item_info(i)
    if recs or rf_recs:
        print(f"Item {i} ({info.get('name')}): used in {len(recs)} classic recipes, {len(rf_recs)} recipe_facts")
        for r in recs[:5]:
            print(f"   Recipe: {r[1]} ({r[2]}, skill {r[3]})")

print("\n=== QUEST USES FOR INVENTORY ITEMS ===")
# Is any inventory item a quest item or acquisition?
for i in inv_ids:
    cur.execute("SELECT id, method, entity_type, entity_id FROM acquisition_facts WHERE item_id = ?", (i,))
    acq = cur.fetchall()
    info = get_item_info(i)
    if acq:
        print(f"Item {i} ({info.get('name')}): {len(acq)} acquisition facts (e.g. {acq[:3]})")

