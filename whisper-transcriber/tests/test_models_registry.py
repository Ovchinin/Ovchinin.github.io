from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import models_info as mi


class ModelsRegistryTests(unittest.TestCase):
    def test_short_revision(self) -> None:
        self.assertEqual(mi.short_revision("abcdef012345"), "abcdef0")
        self.assertEqual(mi.short_revision(""), "—")

    def test_record_and_list_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(mi, "models_dir", return_value=root):
                # fake cached model files
                model_dir = root / "models--Systran--faster-whisper-small"
                model_dir.mkdir()
                (model_dir / "model.bin").write_bytes(b"x" * 2_000_000)
                mi.record_installed_revision("small", "abc1234567890")
                data = json.loads((root / "installed.json").read_text(encoding="utf-8"))
                self.assertEqual(data["small"]["revision"], "abc1234567890")
                installed = mi.list_installed_models()
                self.assertEqual(len(installed), 1)
                self.assertEqual(installed[0].name, "small")
                self.assertEqual(installed[0].short_revision, "abc1234")

    def test_update_available(self) -> None:
        item = mi.InstalledModel(name="small", revision="aaa", remote_revision="bbb", size_gb=0.5)
        self.assertTrue(item.update_available)
        item2 = mi.InstalledModel(name="small", revision="aaa", remote_revision="aaa", size_gb=0.5)
        self.assertFalse(item2.update_available)


if __name__ == "__main__":
    unittest.main()
