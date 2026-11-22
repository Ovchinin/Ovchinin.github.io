from __future__ import annotations

import unittest

from app.setup_dialog import WHISPER_CONSENT_TEXT


class SetupDialogCopyTests(unittest.TestCase):
    def test_consent_mentions_free_and_in_app_install(self) -> None:
        text = WHISPER_CONSENT_TEXT.lower()
        self.assertIn("whisper", text)
        self.assertIn("ffmpeg", text)
        self.assertIn("бесплатн", text)
        self.assertIn("из этого приложения", WHISPER_CONSENT_TEXT)
        self.assertIn("Homebrew", WHISPER_CONSENT_TEXT)
        self.assertIn("не нужн", text)
        self.assertIn("Разрешить установку сейчас?", WHISPER_CONSENT_TEXT)


if __name__ == "__main__":
    unittest.main()
