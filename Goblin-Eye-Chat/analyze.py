import json

with open('af0bd89b_char_data.json') as f:
    d = json.load(f)

print('=== SNAPSHOT SUMMARY ===')
for k, v in d['snapshot_summary'].items():
    if k != 'talents':
        print(f"{k}: {v}")

print('\n=== EQUIPMENT ===')
equip = d.get('equipment', {})
print(json.dumps(equip, indent=2)[:1500])

print('\n=== INVENTORY ===')
inv = d.get('inventory_items', {})
print(json.dumps(inv, indent=2)[:2000])

print('\n=== ACTIVE QUESTS ===')
print(json.dumps(d.get('active_quests'), indent=2)[:1000])

print('\n=== COMPLETED QUESTS ===')
print(json.dumps(d.get('quests'), indent=2)[:1000])

print('\n=== ECONOMIC SUMMARY ===')
print(json.dumps(d.get('economic_summary'), indent=2)[:1000])
