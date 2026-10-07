"""Install only Goblin Eye's owned observation extension into Alts Forever."""
from pathlib import Path
import hashlib
import re
from .discovery import discover_addon_paths

def install_item_export(addon: Path, helper: Path, backup_root: Path):
    addon, helper = Path(addon).resolve(), Path(helper).resolve()
    # Forever selects its edition-specific manifest when one is present.
    # Validate every supported manifest before changing any file.
    tocs = {addon/name:(addon/name).read_text(encoding='utf-8-sig')
            for name in ('AltsForever_Camelot.toc','AltsForever.toc') if (addon/name).is_file()}
    if not tocs:
        raise ValueError('No supported Alts Forever manifest; export extension not installed')
    for toc,text in tocs.items():
        if not re.search(r'^## Interface:\s*16001\s*$',text,re.M):
            raise ValueError(f'Unreviewed Alts Forever interface in {toc.name}; export extension not installed')
        if not re.search(r'^## Version:\s*0\.10\.0\s*$',text,re.M):
            raise ValueError(f'Unreviewed Alts Forever version in {toc.name}; export extension not installed')
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
    if target.is_file() and target.read_bytes()==body and all('GoblinEyeExport.lua' in text.splitlines() for text in tocs.values()):
        return False
    backup=Path(backup_root)/hashlib.sha256(str(addon).encode()).hexdigest()[:12]
    backup.mkdir(parents=True,exist_ok=True)
    for original in (*tocs,target):
        if original.is_file():
            raw=original.read_bytes()
            destination=backup/(original.name+'.'+hashlib.sha256(raw).hexdigest()[:16]+'.bak')
            if not destination.exists(): destination.write_bytes(raw)
    # Copy extension first: an interrupted install cannot leave a TOC referencing a missing file.
    target.write_bytes(body)
    for toc,text in tocs.items():
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
    addons=set(discover_addon_paths('AltsForever','AltsForever_Camelot.toc',candidates))
    addons.update(discover_addon_paths('AltsForever','AltsForever.toc',candidates))
    for addon in sorted(addons,key=str):
        changed=install_item_export(addon,Path(project_root)/'integrations/alts-forever/GoblinEyeExport.lua',
                                    Path(project_root)/'data/addon-backups')
        results.append({'addon':str(addon),'changed':changed})
    return results
