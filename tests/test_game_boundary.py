"""Keep the research backend separate from OS/game-control integrations."""
import ast
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class GameBoundaryTests(unittest.TestCase):
    def test_research_backend_has_no_process_capture_or_input_dependencies(self):
        forbidden={'ctypes','win32api','win32gui','win32process','pyautogui','pynput','psutil','subprocess','mss','PIL','keyboard','mouse'}
        errors=[]
        for path in (ROOT/'src/goblin_eye').rglob('*.py'):
            body=path.read_text(encoding='utf-8-sig')
            for node in ast.walk(ast.parse(body)):
                modules=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                for module in modules:
                    if module.split('.')[0] in forbidden: errors.append(f'{path.name}:{node.lineno}: {module}')
            if re.search(r'\b(ReadProcessMemory|WriteProcessMemory|SendInput|SetForegroundWindow|SetCursorPos|CreateRemoteThread|VirtualAllocEx)\b',body):
                errors.append(f'{path.name}: game/OS access symbol')
        self.assertEqual(errors,[], '\n'.join(errors))

    def test_observation_extension_has_no_gameplay_actions(self):
        body=(ROOT/'integrations/alts-forever/GoblinEyeExport.lua').read_text(encoding='utf-8')
        forbidden=r'\b(RunMacroText|RunScript|CastSpellByName|CastSpellByID|UseAction|UseContainerItem|PickupContainerItem|TargetUnit|InteractUnit|StartAttack|MoveForwardStart|JumpOrAscendStart|PlaceAuctionBid|PostAuction|SendChatMessage)\s*\('
        self.assertIsNone(re.search(forbidden,body))
        self.assertIn('C_TooltipInfo.GetHyperlink',body)
        self.assertIn('ns.char.goblinEyeCharacter',body)

if __name__=='__main__': unittest.main()
