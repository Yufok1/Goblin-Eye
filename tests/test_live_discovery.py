from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from goblin_eye.ingestion import discovery


class LiveDiscoveryTests(unittest.TestCase):
    def test_live_never_imports_missing_sources_from_beta(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            beta_addon = root / '_classic_beta_/Interface/AddOns/QuestieDB'
            beta_addon.mkdir(parents=True)
            (beta_addon / 'QuestieDB_Forever.toc').write_text('beta')
            beta_save = root / '_classic_beta_/WTF/Account/TEST/SavedVariables/AHledger.lua'
            beta_save.parent.mkdir(parents=True)
            beta_save.write_text('beta')
            with patch.object(discovery, 'WOW_ROOTS', (root,)):
                self.assertEqual(discovery.discover_saved_files('AHledger.lua'), [beta_save.resolve()])
                (root / '_forever_').mkdir()
                self.assertEqual(discovery.discover_saved_files('AHledger.lua'), [])
                self.assertEqual(discovery.discover_addon_paths('QuestieDB', 'QuestieDB_Forever.toc'), [])
                live_save = root / '_forever_/WTF/Account/TEST/SavedVariables/AHledger.lua'
                live_save.parent.mkdir(parents=True)
                live_save.write_text('live')
                self.assertEqual(discovery.discover_saved_files('AHledger.lua'), [live_save.resolve()])

    def test_explicit_paths_exclude_other_installs_even_before_capture(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            auto_addon = root / '_forever_/Interface/AddOns/QuestieDB'
            auto_addon.mkdir(parents=True)
            (auto_addon / 'QuestieDB_Forever.toc').write_text('auto')
            auto_save = root / '_forever_/WTF/Account/OTHER/SavedVariables/AHledger.lua'
            auto_save.parent.mkdir(parents=True)
            auto_save.write_text('auto')
            selected_addon = root / 'selected/QuestieDB'
            selected_save = root / 'selected/AHledger.lua'
            with patch.object(discovery, 'WOW_ROOTS', (root,)):
                self.assertEqual(discovery.discover_saved_files('AHledger.lua', (str(selected_save),)), [])
                self.assertEqual(discovery.discover_addon_paths('QuestieDB', 'QuestieDB_Forever.toc', (str(selected_addon),)), [])
                selected_addon.mkdir(parents=True)
                selected_save.write_text('selected')
                (selected_addon / 'QuestieDB_Forever.toc').write_text('selected')
                self.assertEqual(discovery.discover_saved_files('AHledger.lua', (str(selected_save),)), [selected_save.resolve()])
                self.assertEqual(discovery.discover_addon_paths('QuestieDB', 'QuestieDB_Forever.toc', (str(selected_addon),)), [selected_addon.resolve()])


if __name__ == '__main__':
    unittest.main()
