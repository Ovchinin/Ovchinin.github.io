from __future__ import annotations

import customtkinter as ctk

from .installer import DependencyStatus
from .theme import COLOR, PRIMARY_BTN, SECONDARY_BTN, F, apply_appearance


WHISPER_CONSENT_TEXT = """Для работы «Транскрибация» нужно установить Whisper и ffmpeg — бесплатные компоненты распознавания речи и извлечения звука из видео.

Что это значит:
• Всё бесплатно: без подписок и оплаты за минуты
• Установка выполнится прямо из этого приложения — Homebrew и ручные команды не нужны
• Распознавание идёт на вашем Mac, аудио в облако не отправляется
• При первой транскрибации дополнительно скачается модель Whisper (один раз)

Разрешить установку сейчас?"""


class WhisperSetupDialog(ctk.CTkToplevel):
    """Модальный диалог: объяснить необходимость Whisper и запросить согласие."""

    def __init__(self, master: ctk.CTk, status: DependencyStatus) -> None:
        super().__init__(master)
        apply_appearance()
        self.configure(fg_color=COLOR["bg"])
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

        pad = {"padx": 28}

        ctk.CTkLabel(
            self,
            text="Установка Whisper",
            font=F(22, "bold"),
            text_color=COLOR["ink"],
            anchor="w",
        ).pack(anchor="w", pady=(26, 6), **pad)

        ctk.CTkFrame(self, height=2, width=40, fg_color=COLOR["accent"], corner_radius=1).pack(
            anchor="w", padx=28, pady=(0, 12)
        )

        ctk.CTkLabel(
            self,
            text=f"Не найдено: {missing_line}",
            font=F(12),
            text_color=COLOR["muted"],
            anchor="w",
        ).pack(anchor="w", pady=(0, 10), **pad)

        body = ctk.CTkTextbox(
            self,
            width=460,
            height=250,
            wrap="word",
            font=F(13),
            fg_color=COLOR["surface"],
            text_color=COLOR["ink"],
            border_width=1,
            border_color=COLOR["line"],
            corner_radius=8,
        )
        body.pack(fill="both", expand=True, padx=28, pady=(0, 14))
        body.insert("1.0", WHISPER_CONSENT_TEXT)
        body.configure(state="disabled")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=28, pady=(0, 24))

        ctk.CTkButton(
            buttons,
            text="Позже",
            width=120,
            height=36,
            font=F(13),
            command=self._decline,
            **SECONDARY_BTN,
        ).pack(side="left")

        ctk.CTkButton(
            buttons,
            text="Установить бесплатно",
            width=200,
            height=36,
            font=F(13, "bold"),
            command=self._accept,
            **PRIMARY_BTN,
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
