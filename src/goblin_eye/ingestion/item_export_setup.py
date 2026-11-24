"""Install only Goblin Eye's owned observation extension into Alts Forever."""
from pathlib import Path
import hashlib
import re
from .discovery import discover_addon_paths

# Reviewed schema v2 and scanner contracts. Unknown releases still require review.
# Live 1.0.1 retains DB v2, full-link slot keys, incomplete-gear return value,
# container argument layout, ns.db/ns.char and the event registration contract.
# 1.7.0 retains these contracts; ScanGear also returns a changed flag, which
# the extension preserves. Its dispatcher safely ignores unsupported events.
# 1.8.0 retains DB v2 and adds a fourth ScanContainers argument for retained
# variant links. The owned wrapper must forward it to preserve addon behavior.
# 1.9.1 retains these schema, scanner, score and event-dispatch contracts.
REVIEWED_ALTS_VERSIONS = frozenset(('0.10.0', '0.13.0', '0.16.0', '1.0.1', '1.7.0', '1.8.0', '1.9.1'))


def validate_item_export_contract(addon: Path):
    """Check compatibility without installing or changing addon files."""
    addon = Path(addon).resolve()
    # Forever selects its edition-specific manifest when one is present.
    # Validate every supported manifest before changing any file.
    tocs = {addon/name:(addon/name).read_text(encoding='utf-8-sig')
            for name in ('AltsForever_Camelot.toc','AltsForever.toc') if (addon/name).is_file()}
    if not tocs:
        raise ValueError('No supported Alts Forever manifest; export extension not installed')
    versions = set()
    for toc,text in tocs.items():
        if not re.search(r'^## Interface:\s*16001\s*$',text,re.M):
            raise ValueError(f'Unreviewed Alts Forever interface in {toc.name}; export extension not installed')
        version = re.search(r'^## Version:\s*(\S+)\s*$',text,re.M)
        if not version or version[1] not in REVIEWED_ALTS_VERSIONS:
            found = version[1] if version else 'missing'
            raise ValueError(f'Unreviewed Alts Forever version {found} in {toc.name}; export extension not installed')
        versions.add(version[1])
        loaded = {line.strip() for line in text.splitlines()}
        if not {'Core.lua', 'Gear.lua', 'Scanner.lua', 'Upgrades.lua'} <= loaded:
            raise ValueError(f'Alts Forever scanner files missing from {toc.name}; export extension not installed')
    if len(versions) != 1:
        raise ValueError('Alts Forever manifest versions disagree; export extension not installed')
    containers = (r'^function ns\.ScanContainers\(\s*bags\s*,\s*out\s*,\s*layout\s*,\s*links\s*\)'
                  if versions <= {'1.8.0', '1.9.1'} else r'^function ns\.ScanContainers\(\s*bags\s*,\s*out\s*,\s*layout\s*\)')
    contracts = (
        ('Gear.lua', r'^function ns\.ScanGear\(\s*c\s*\)'),
        ('Scanner.lua', containers),
        ('Upgrades.lua', r'^function ns\.ItemScore\(\s*link\s*,\s*role\s*\)'),
        ('Core.lua', r'^function ns\.On\(\s*event\s*,\s*fn\s*\)'),
    )
    for name, pattern in contracts:
        source = (addon/name).read_text(encoding='utf-8-sig')
        if not re.search(pattern, source, re.M):
            raise ValueError('Alts Forever scanner contract changed; review before installing export')
        if name == 'Core.lua' and not re.search(r'^local DB_VERSION\s*=\s*2\s*$', source, re.M):
            raise ValueError('Alts Forever saved schema changed; export extension not installed')
    return tocs


def install_item_export(addon: Path, helper: Path, backup_root: Path):
    addon, helper = Path(addon).resolve(), Path(helper).resolve()
    tocs = validate_item_export_contract(addon)
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
