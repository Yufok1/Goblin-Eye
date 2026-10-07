"""Install only Goblin Eye's owned observation extension into Alts Forever."""
from pathlib import Path
import hashlib
import re
from .discovery import discover_addon_paths

def install_item_export(addon: Path, helper: Path, backup_root: Path):
    addon, helper = Path(addon).resolve(), Path(helper).resolve()
    toc = addon/'AltsForever.toc'
    text = toc.read_text(encoding='utf-8-sig')
    if not re.search(r'^## Interface:\s*16001\s*$',text,re.M):
        raise ValueError('Unreviewed Alts Forever interface; export extension not installed')
    if not re.search(r'^## Version:\s*0\.10\.0\s*$',text,re.M):
        raise ValueError('Unreviewed Alts Forever version; export extension not installed')
    for name, marker in (('Gear.lua','function ns.ScanGear('),('Scanner.lua','function ns.ScanContainers('),
                         ('Upgrades.lua','function ns.ItemScore('),('Core.lua','function ns.On(')):
        if marker not in (addon/name).read_text(encoding='utf-8-sig'):
            raise ValueError('Alts Forever scanner contract changed; review before installing export')
    body=helper.read_bytes()
    target=addon/'GoblinEyeExport.lua'
    if target.is_file() and target.read_bytes()!=body:
        existing=target.read_bytes()
        if not existing.startswith(b'-- Goblin Eye\'s optional observation export'):
            raise ValueError('Foreign GoblinEyeExport.lua exists; refusing to overwrite it')
    if target.is_file() and target.read_bytes()==body and 'GoblinEyeExport.lua' in text.splitlines():
        return False
    backup=Path(backup_root)/hashlib.sha256(str(addon).encode()).hexdigest()[:12]
    backup.mkdir(parents=True,exist_ok=True)
    for original in (toc,target):
        if original.is_file():
            raw=original.read_bytes()
            destination=backup/(original.name+'.'+hashlib.sha256(raw).hexdigest()[:16]+'.bak')
            if not destination.exists(): destination.write_bytes(raw)
    # Copy extension first: an interrupted install cannot leave a TOC referencing a missing file.
    target.write_bytes(body)
    if 'GoblinEyeExport.lua' not in text.splitlines():
        toc.write_text(text.rstrip()+'\nGoblinEyeExport.lua\n',encoding='utf-8')
    return True

def ensure_item_exports(project_root: Path, saved_paths=()):
    candidates=[]
    for saved in saved_paths:
        path=Path(saved).resolve()
        # Only the known SavedVariables hierarchy supplies an installation root.
        if path.name=='AltsForever.lua' and path.parent.name=='SavedVariables' and len(path.parents)>4:
            client=path.parents[4]
            candidates.append(str(client/'Interface/AddOns/AltsForever'))
    results=[]
    for addon in discover_addon_paths('AltsForever','AltsForever.toc',candidates):
        changed=install_item_export(addon,Path(project_root)/'integrations/alts-forever/GoblinEyeExport.lua',
                                    Path(project_root)/'data/addon-backups')
        results.append({'addon':str(addon),'changed':changed})
    return results
