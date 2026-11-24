from pathlib import Path
from goblin_eye.config import Settings
from goblin_eye.repository.database import Database
from goblin_eye.services import ResearchService
import json

cfg = Settings.load(Path('D:/End-Game/ended_game/codex_playground/Goblin-Eye/config.json'))
db = Database(cfg.database_path)
svc = ResearchService(db, cfg)

inv_ids = [1180, 1210, 3174, 5058, 5165, 5511, 6624, 6915, 6948, 16189, 16746, 20558, 248682, 248683, 248685, 248702, 250187]
print("--- INVENTORY ITEMS ---")
for i in inv_ids:
    it = svc.item(i)
    if it:
        print(f"{i}: {it.get('name')} | quality: {it.get('quality')} | level: {it.get('item_level')} | req: {it.get('required_level')} | item_class: {it.get('item_class')}/{it.get('item_subclass')}")
    else:
        print(f"{i}: NOT FOUND IN SERVICE")

print("\n--- EQUIPPED ITEMS ---")
equip_ids = [281265, 10657, 14133, 2911, 6568, 14374, 3647, 270030, 6414, 11982, 12979, 273637, 5323, 8186]
for i in equip_ids:
    it = svc.item(i)
    if it:
        print(f"{i}: {it.get('name')} | quality: {it.get('quality')} | level: {it.get('item_level')} | req: {it.get('required_level')} | item_class: {it.get('item_class')}/{it.get('item_subclass')}")
    else:
        print(f"{i}: NOT FOUND IN SERVICE")
