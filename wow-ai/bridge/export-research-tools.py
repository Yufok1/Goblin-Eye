"""Generate the bridge allowlist from the actual read-only MCP registry."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'src'))
from goblin_eye.mcp_server import TOOLS

names = sorted(t['name'] for t in TOOLS if t.get('annotations', {}).get('readOnlyHint') is True)
if not names or len(names) != len(set(names)):
    raise ValueError('Invalid MCP tool registry')
target = root / 'wow-ai/bridge/research-tools.json'
temporary = target.with_suffix('.json.tmp')
temporary.write_text(json.dumps(names, indent=2) + '\n', encoding='utf-8')
temporary.replace(target)
print(f'Research policy: {len(names)} read-only tools.')
