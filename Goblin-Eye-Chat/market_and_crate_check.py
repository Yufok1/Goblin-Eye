import sqlite3
import json

db_path = r'D:\End-Game\ended_game\codex_playground\Goblin-Eye\data\forever-live\goblin-eye.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== AUCTION MARKET CHECK ===")
for item_id in [1210, 3174, 5165, 250187]:
    cur.execute("SELECT item_id, minimum_copper, median_copper, available_quantity, observed_date FROM market_price_points WHERE item_id = ?", (item_id,))
    rows = cur.fetchall()
    print(f"Item {item_id} price points: {rows}")
    cur.execute("SELECT item_id, buyout_copper, quantity, time_left_code FROM auction_rows WHERE item_id = ? LIMIT 5", (item_id,))
    arows = cur.fetchall()
    print(f"Item {item_id} auction rows: {arows}")

# Check recipe details for 250187
cur.execute("SELECT attributes_json FROM item_property_facts WHERE item_id = 250187")
r = cur.fetchone()
if r:
    print("\n250187 properties:", r[0])

# Check Waylaid Crates 248682, 248683, 248685, 248702
for cid in [248682, 248683, 248685, 248702]:
    cur.execute("SELECT attributes_json FROM item_property_facts WHERE item_id = ?", (cid,))
    r = cur.fetchone()
    if r:
        print(f"\nCrate {cid} properties:", r[0])
