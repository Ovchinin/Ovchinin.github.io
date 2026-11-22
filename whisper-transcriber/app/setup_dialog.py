from __future__ import annotations

import customtkinter as ctk

from .installer import DependencyStatus


WHISPER_CONSENT_TEXT = """Для работы «Транскрибация» нужно установить Whisper — бесплатный движок распознавания речи от OpenAI.

Что это значит:
• Whisper бесплатный: без подписок и оплаты за минуты
• Установка выполнится прямо из этого приложения — вручную ничего ставить не нужно
• Распознавание идёт на вашем Mac, аудио в облако не отправляется
• При первой транскрибации дополнительно скачается модель (один раз)

Также может понадобиться ffmpeg для извлечения звука из видео — его приложение тоже поставит само (через Homebrew, если он есть).

Разрешить установку сейчас?"""


class WhisperSetupDialog(ctk.CTkToplevel):
    """Модальный диалог: объяснить необходимость Whisper и запросить согласие."""

    def __init__(self, master: ctk.CTk, status: DependencyStatus) -> None:
        super().__init__(master)
        self.title("Транскрибация — установка Whisper")
        self.geometry("520x460")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: bool | None = None

        missing: list[str] = []
        if not status.whisper_ok:
            missing.append("Whisper (faster-whisper)")
        if not status.ffmpeg_ok:
            missing.append("ffmpeg")
        missing_line = ", ".join(missing) if missing else "компоненты распознавания"

        pad = {"padx": 24}

        ctk.CTkLabel(
            self,
            text="Установка для работы «Транскрибация»",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(22, 8), **pad)

        ctk.CTkLabel(
            self,
            text=f"Не найдено: {missing_line}",
            text_color=("gray30", "gray70"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 10), **pad)

        body = ctk.CTkTextbox(self, width=470, height=260, wrap="word")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        body.insert("1.0", WHISPER_CONSENT_TEXT)
        body.configure(state="disabled")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(0, 20))

        ctk.CTkButton(
            buttons,
            text="Позже",
            width=120,
            fg_color=("gray75", "gray35"),
            command=self._decline,
        ).pack(side="left")

        ctk.CTkButton(
            buttons,
            text="Установить бесплатно",
            width=200,
            command=self._accept,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._decline)
        self.after(50, self._focus)

    def _focus(self) -> None:
        self.lift()
        self.focus_force()

    def _accept(self) -> None:
        self.result = True
        self.grab_release()
        self.destroy()

    def _decline(self) -> None:
        self.result = False
        self.grab_release()
        self.destroy()


def ask_whisper_install_consent(master: ctk.CTk, status: DependencyStatus) -> bool:
    dialog = WhisperSetupDialog(master, status)
    master.wait_window(dialog)
    return bool(dialog.result)