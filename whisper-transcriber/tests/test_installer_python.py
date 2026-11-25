from __future__ import annotations

import unittest

from app import installer


class PythonSupportTests(unittest.TestCase):
    def test_supported_range(self) -> None:
        self.assertTrue(installer.python_supported((3, 10)))
        self.assertTrue(installer.python_supported((3, 12)))
        self.assertTrue(installer.python_supported((3, 13)))
        self.assertFalse(installer.python_supported((3, 9)))
        self.assertFalse(installer.python_supported((3, 14)))

    def test_message_mentions_314(self) -> None:
        msg = installer.python_requirement_message()
        self.assertIn("3.14", msg)
        self.assertIn("onnxruntime", msg)


if __name__ == "__main__":
    unittest.main()
