"""Keep the addon upload compatible and exclude installed/private transport data."""
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("curseforge", ROOT / "scripts/build_curseforge.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class CurseForgePackageTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="goblin-eye-addon-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        names = [f"{package.ADDON}/{name}" for name in package.ADDON_FILES]
        names += [*package.DOCUMENTS.values(), "config.example.json"]
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        return root

    def test_only_reviewed_assets_reach_deterministic_archive(self):
        root = self.fixture()
        for name in ("config.json", "data/private.db", "wow-ai/bridge/config.json",
                     "wow-ai/addon/WoWAI/sig/001.wav", "wow-ai/addon/WoWAI/private.lua",
                     "wow-ai/addon/WoWAI_S001/Inbox.lua"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private runtime fixture", encoding="utf-8")
        first, second = root / "first.zip", root / "second.zip"
        report = package.build(first, root)
        package.build(second, root)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertFalse(report["personal_data_included"])
        self.assertFalse(report["curseforge_uploaded"])
        with zipfile.ZipFile(first) as archive:
            self.assertEqual({Path(name).parts[0] for name in archive.namelist()}, {"WoWAI"})
            self.assertIn("WoWAI/WoWAI.toc", archive.namelist())
            self.assertIn("WoWAI/LICENSE", archive.namelist())
            self.assertIn("WoWAI/GOBLIN-EYE-LICENSE", archive.namelist())
            self.assertEqual(archive.read("WoWAI/WoWAI.lua"),
                             (ROOT / package.ADDON / "WoWAI.lua").read_bytes())
            self.assertFalse(any(b"private runtime fixture" in archive.read(name)
                                 for name in archive.namelist()))
        self.assertEqual(json.loads(first.with_suffix(".validation.json").read_text()), report)

    def test_private_inbox_is_rejected_even_at_repository_path(self):
        root = self.fixture()
        (root / package.ADDON / "Inbox.lua").write_text(
            "WoWAI_Inbox = { replies = {'private chat'} }", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty repository template"):
            package.collect(root)

    def test_manifest_cannot_reference_missing_payload(self):
        files = package.collect()
        files["WoWAI/WoWAI.toc"] += b"\nMissing.lua\n"
        with self.assertRaisesRegex(ValueError, "unpackaged file"):
            package.validate(files)

    def test_undeclared_file_cannot_be_added(self):
        files = package.collect()
        files["WoWAI/config.json"] = b"{}"
        with self.assertRaisesRegex(ValueError, "allowlist"):
            package.validate(files)

    def test_target_interface_and_saved_variables_require_review(self):
        for before, after in ((b"16001", b"99999"),
                              (b"WoWAIDB, WoWAIMapDB", b"RenamedDB")):
            files = package.collect()
            files["WoWAI/WoWAI.toc"] = files["WoWAI/WoWAI.toc"].replace(before, after)
            with self.subTest(after=after), self.assertRaises(ValueError):
                package.validate(files)
