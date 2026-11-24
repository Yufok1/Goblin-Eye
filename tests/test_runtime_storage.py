"""Filesystem-only checks; no services, CLI agents, speech or game clients."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goblin_eye.runtime_storage import configure, validate_storage


class RuntimeStorageTests(unittest.TestCase):
    def test_windows_storage_rejects_system_drive_and_unc(self):
        for target in (r"C:\data", "c:/data", "D:relative", "relative", r"\\host\share\data"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_storage(target, platform="win32")
        validate_storage(r"D:\Goblin Eye\data", platform="win32")

    def test_configure_redirects_temp_caches_and_profiles(self):
        with tempfile.TemporaryDirectory(prefix="goblin-storage-") as work:
            root = Path(work) / "runtime"
            original_temp = tempfile.tempdir
            try:
                with patch.dict(os.environ, {"GOBLIN_EYE_STORAGE_ROOT": str(root), "TEMP": r"C:\old-temp"}):
                    self.assertEqual(configure(), root)
                    spec = json.loads((Path(__file__).resolve().parents[1] / "runtime-storage.json").read_text())
                    for key, relative in spec["directories"].items():
                        self.assertEqual(Path(os.environ[key]), root / relative, key)
                        self.assertTrue((root / relative).is_dir(), key)
                    self.assertEqual(Path(tempfile.gettempdir()), root / "tmp")
            finally:
                tempfile.tempdir = original_temp
