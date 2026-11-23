from __future__ import annotations

import subprocess
import threading
import time
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import __version__
from .engine import ProgressUpdate, TranscriptionCancelled, transcribe_media
from .export import SAVE_AS_FILETYPES, write_export
from .installer import DependencyStatus, check_dependencies, ensure_dependencies
from .models_info import (
    MODEL_ORDER,
    all_models_legend,
    format_avg_wait,
    format_size_gb,
    get_model_info,
    is_model_cached,
    model_label_for_ui,
)
from .settings import AppSettings
from .setup_dialog import ask_whisper_install_consent
from .theme import (
    COLOR,
    GHOST_BTN,
    PRIMARY_BTN,
    SECONDARY_BTN,
    F,
    apply_appearance,
)


VIDEO_TYPES = [
    ("Видео / аудио", "*.mp4 *.mov *.m4v *.mkv *.avi *.webm *.mp3 *.m4a *.wav *.aac *.flac"),
    ("Все файлы", "*.*"),
]

MODEL_CHOICES = list(MODEL_ORDER)
MODEL_MENU_VALUES = [model_label_for_ui(name) for name in MODEL_CHOICES]

_COPY_BTN_LABEL = "Скопировать результат"
_COPIED_BTN_LABEL = "Скопировано"
_SAVE_AS_LABEL = "Сохранить как…"
_ICON_PX = 13


def _draw_copy_glyph(size: int, fill: tuple[int, int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    stroke = max(2, round(size / 10))
    radius = max(2, round(size / 10))
    draw.rounded_rectangle(
        (size * 0.28, size * 0.06, size * 0.94, size * 0.72),
        radius=radius,
        outline=fill,
        width=stroke,
    )
    draw.rounded_rectangle(
        (size * 0.06, size * 0.28, size * 0.72, size * 0.94),
        radius=radius,
        outline=fill,
        width=stroke,
    )
    return img


def _draw_check_glyph(size: int, fill: tuple[int, int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w = max(2, round(size / 8))
    points = [
        (size * 0.14, size * 0.52),
        (size * 0.40, size * 0.78),
        (size * 0.88, size * 0.22),
    ]
    draw.line(points, fill=fill, width=w, joint="curve")
    return img


def _make_btn_icon(kind: str = "copy") -> ctk.CTkImage:
    master = _ICON_PX * 4
    light = (26, 25, 23, 255)
    dark = (243, 241, 236, 255)
    drawer = _draw_copy_glyph if kind == "copy" else _draw_check_glyph
    return ctk.CTkImage(
        light_image=drawer(master, light),
        dark_image=drawer(master, dark),
        size=(_ICON_PX, _ICON_PX),
    )


def _model_name_from_menu(label: str) -> str:
    name = (label or "").split(" — ", 1)[0].strip()
    return name if name in MODEL_CHOICES else "small"


def _fmt_eta(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ч {m:02d} мин"
    if m:
        return f"{m} мин {s:02d} с"
    return f"{s} с"


def _fmt_speed(speed_x: float | None) -> str:
    if speed_x is None or speed_x <= 0:
        return "—"
    return f"{speed_x:.2f}×"


class WhisperApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        apply_appearance()
        self.configure(fg_color=COLOR["bg"])

        self.title(f"Транскрибация {__version__}")
        self.geometry("860x800")
        self.minsize(760, 700)

        self.settings = AppSettings.load()
        self.source_path: Path | None = None
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._last_tick = time.time()
        self._last_result_text = ""
        self._last_result_stem = "transcript"

        self._build()
        self.after(200, self._bootstrap_deps)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # —— Editorial hero ——
        hero = ctk.CTkFrame(self, fg_color="transparent")
        hero.grid(row=0, column=0, sticky="ew", padx=40, pady=(32, 6))
        hero.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hero,
            text="Транскрибация",
            font=F(30, "bold"),
            text_color=COLOR["ink"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            hero,
            text="Видео и аудио → читаемый русский текст. Локально, через Whisper.",
            font=F(13),
            text_color=COLOR["muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        ctk.CTkFrame(hero, height=2, width=56, fg_color=COLOR["ink"], corner_radius=1).grid(
            row=2, column=0, sticky="w", pady=(16, 0)
        )

        # —— Form ——
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=1, column=0, sticky="ew", padx=40, pady=(18, 4))
        form.grid_columnconfigure(1, weight=1)

        def _label(row: int, text: str) -> None:
            ctk.CTkLabel(
                form,
                text=text,
                font=F(12),
                text_color=COLOR["muted"],
                anchor="w",
                width=64,
            ).grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=(10, 0))

        _label(0, "Файл")
        self.source_var = tk.StringVar(value="Файл не выбран")
        ctk.CTkEntry(
            form,
            textvariable=self.source_var,
            state="readonly",
            font=F(13),
            fg_color=COLOR["surface"],
            border_color=COLOR["entry_border"],
            border_width=1,
            text_color=COLOR["ink"],
            corner_radius=8,
            height=36,
        ).grid(row=0, column=1, sticky="ew", pady=6)
        ctk.CTkButton(
            form,
            text="Выбрать",
            width=104,
            height=36,
            font=F(13),
            command=self._pick_source,
            **SECONDARY_BTN,
        ).grid(row=0, column=2, padx=(10, 0), pady=6)

        _label(1, "Папка")
        self.output_var = tk.StringVar(value=self.settings.output_dir)
        ctk.CTkEntry(
            form,
            textvariable=self.output_var,
            font=F(13),
            fg_color=COLOR["surface"],
            border_color=COLOR["entry_border"],
            border_width=1,
            text_color=COLOR["ink"],
            corner_radius=8,
            height=36,
        ).grid(row=1, column=1, sticky="ew", pady=(6, 0))
        ctk.CTkButton(
            form,
            text="Куда",
            width=104,
            height=36,
            font=F(13),
            command=self._pick_output,
            **SECONDARY_BTN,
        ).grid(row=1, column=2, padx=(10, 0), pady=(6, 0))

        ctk.CTkLabel(
            form,
            text="По умолчанию результат сохраняется в текстовом файле (.txt).",
            font=F(11),
            text_color=COLOR["faint"],
            anchor="w",
            justify="left",
            wraplength=560,
        ).grid(row=2, column=1, columnspan=2, sticky="w", pady=(4, 2))

        _label(3, "Модель")
        initial_model = self.settings.model_size if self.settings.model_size in MODEL_CHOICES else "small"
        self.model_var = tk.StringVar(value=model_label_for_ui(initial_model))
        ctk.CTkOptionMenu(
            form,
            values=MODEL_MENU_VALUES,
            variable=self.model_var,
            width=340,
            height=36,
            font=F(13),
            dropdown_font=F(13),
            fg_color=COLOR["surface"],
            button_color=COLOR["muted_surface"],
            button_hover_color=COLOR["line"],
            text_color=COLOR["ink"],
            dropdown_fg_color=COLOR["surface"],
            dropdown_hover_color=COLOR["muted_surface"],
            dropdown_text_color=COLOR["ink"],
            corner_radius=8,
            command=lambda _v: self._refresh_model_hint(),
        ).grid(row=3, column=1, sticky="w", pady=6)

        self.model_hint = ctk.CTkLabel(
            form,
            text="",
            font=F(12),
            text_color=COLOR["faint"],
            anchor="w",
            justify="left",
            wraplength=580,
        )
        self.model_hint.grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 2))

        self._models_info_expanded = False
        self.models_toggle_btn = ctk.CTkButton(
            form,
            text="Больше о моделях",
            anchor="w",
            font=F(12),
            height=26,
            command=self._toggle_models_info,
            **GHOST_BTN,
        )
        self.models_toggle_btn.grid(row=5, column=1, columnspan=2, sticky="w", pady=(2, 2))

        self.models_legend = ctk.CTkLabel(
            form,
            text=all_models_legend(),
            font=F(12),
            text_color=COLOR["muted"],
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self._refresh_model_hint()

        self.notify_var = tk.BooleanVar(value=self.settings.notify_on_complete)
        ctk.CTkCheckBox(
            form,
            text="Получить уведомление об окончании выполнения операции",
            variable=self.notify_var,
            command=self._persist_form_settings,
            font=F(12),
            text_color=COLOR["ink"],
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hover"],
            border_color=COLOR["entry_border"],
            checkmark_color=COLOR["surface"],
            corner_radius=3,
        ).grid(row=7, column=1, columnspan=2, sticky="w", pady=(12, 4))

        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=8, column=0, columnspan=3, sticky="e", pady=(16, 4))

        self.install_btn = ctk.CTkButton(
            actions,
            text="Установить Whisper",
            width=168,
            height=36,
            font=F(13),
            command=self._offer_install,
            **SECONDARY_BTN,
        )
        self.install_btn.grid(row=0, column=0, padx=(0, 8))
        self.install_btn.grid_remove()

        self.cancel_btn = ctk.CTkButton(
            actions,
            text="Отмена",
            width=96,
            height=36,
            font=F(13),
            command=self._cancel,
            state="disabled",
            **SECONDARY_BTN,
        )
        self.cancel_btn.grid(row=0, column=1, padx=(0, 8))

        self.start_btn = ctk.CTkButton(
            actions,
            text="Транскрибировать",
            width=168,
            height=36,
            font=F(13, "bold"),
            command=self._start,
            **PRIMARY_BTN,
        )
        self.start_btn.grid(row=0, column=2)

        # —— Result ——
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=40, pady=(10, 28))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(4, weight=1)

        ctk.CTkFrame(body, height=1, fg_color=COLOR["line"], corner_radius=0).grid(
            row=0, column=0, sticky="ew"
        )

        self.stage_label = ctk.CTkLabel(
            body,
            text="Ожидание файла",
            font=F(12),
            text_color=COLOR["muted"],
            anchor="w",
        )
        self.stage_label.grid(row=1, column=0, sticky="ew", pady=(14, 6))

        self.progress = ctk.CTkProgressBar(
            body,
            height=4,
            corner_radius=2,
            progress_color=COLOR["progress"],
            fg_color=COLOR["progress_track"],
        )
        self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.progress.set(0)

        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1)

        self.pct_label = ctk.CTkLabel(stats, text="0%", font=F(12), text_color=COLOR["faint"])
        self.pct_label.grid(row=0, column=0, sticky="w")
        self.speed_label = ctk.CTkLabel(
            stats, text="Скорость: —", font=F(12), text_color=COLOR["faint"]
        )
        self.speed_label.grid(row=0, column=1)
        self.eta_label = ctk.CTkLabel(
            stats, text="Осталось: —", font=F(12), text_color=COLOR["faint"]
        )
        self.eta_label.grid(row=0, column=2, sticky="e")

        result_panel = ctk.CTkFrame(
            body,
            fg_color=COLOR["surface"],
            border_width=0,
            corner_radius=12,
        )
        result_panel.grid(row=4, column=0, sticky="nsew")
        result_panel.grid_columnconfigure(0, weight=1)
        result_panel.grid_rowconfigure(1, weight=1)

        self.result_title = ctk.CTkLabel(
            result_panel,
            text="Результат работы",
            anchor="w",
            font=F(14, "bold"),
            text_color=COLOR["ink"],
        )
        self.result_title.grid(row=0, column=0, sticky="w", padx=18, pady=(16, 6))

        self.preview = ctk.CTkTextbox(
            result_panel,
            wrap="word",
            font=F(13),
            fg_color=COLOR["surface"],
            text_color=COLOR["ink"],
            border_width=0,
            corner_radius=0,
            scrollbar_button_color=COLOR["line"],
            scrollbar_button_hover_color=COLOR["muted"],
        )
        self.preview.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        self.preview.insert("1.0", "Здесь появится результат транскрибации.\n")
        self.preview.configure(state="disabled")
        self._result_ready = False

        result_actions = ctk.CTkFrame(body, fg_color="transparent")
        result_actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        result_actions.grid_columnconfigure(0, weight=1)

        self._copy_icon = _make_btn_icon("copy")
        self._copied_icon = _make_btn_icon("check")
        self.copy_btn = ctk.CTkButton(
            result_actions,
            text=_COPY_BTN_LABEL,
            image=self._copy_icon,
            compound="left",
            width=210,
            height=34,
            font=F(12),
            command=self._copy_result,
            state="disabled",
            **SECONDARY_BTN,
        )
        self.copy_btn.grid(row=0, column=0, sticky="w")

        self.save_as_btn = ctk.CTkButton(
            result_actions,
            text=_SAVE_AS_LABEL,
            width=140,
            height=34,
            font=F(12),
            command=self._save_as,
            state="disabled",
            **SECONDARY_BTN,
        )
        self.save_as_btn.grid(row=0, column=1, sticky="e")

    def _bootstrap_deps(self) -> None:
        status = check_dependencies()
        self._apply_deps_status(status)
        if not status.ready:
            self.after(100, lambda: self._offer_install(status=status, auto_prompt=True))

    def _apply_deps_status(self, status: DependencyStatus) -> None:
        if status.ready:
            self.install_btn.grid_remove()
            self.start_btn.configure(state="normal")
        else:
            self.install_btn.grid()
            self.start_btn.configure(state="disabled")

    def _offer_install(
        self,
        status: DependencyStatus | None = None,
        auto_prompt: bool = False,
    ) -> None:
        if self.worker and self.worker.is_alive():
            return
        status = status or check_dependencies()
        if status.ready:
            self._apply_deps_status(status)
            if not auto_prompt:
                messagebox.showinfo("Готово", "Whisper уже установлен и готов к работе.")
            return

        consented = ask_whisper_install_consent(self, status)
        if not consented:
            self.install_btn.grid()
            self.start_btn.configure(state="disabled")
            return

        self._install_deps()

    def _pick_source(self) -> None:
        path = filedialog.askopenfilename(title="Выберите видео или аудио", filetypes=VIDEO_TYPES)
        if not path:
            return
        self.source_path = Path(path)
        self.source_var.set(str(self.source_path))

    def _pick_output(self) -> None:
        initial = self.output_var.get() or self.settings.output_dir
        path = filedialog.askdirectory(title="Куда сохранить текст", initialdir=initial)
        if not path:
            return
        self.output_var.set(path)
        self.settings.output_dir = path
        self.settings.save()

    def _selected_model(self) -> str:
        return _model_name_from_menu(self.model_var.get())

    def _refresh_model_hint(self) -> None:
        name = self._selected_model()
        info = get_model_info(name)
        cached = is_model_cached(name)
        status = "уже на диске" if cached else "скачается при первом запуске"
        self.model_hint.configure(
            text=(
                f"{info.name}: {format_size_gb(info.size_gb)}, "
                f"скачивание {format_avg_wait(info.avg_download_min)} "
                f"({info.eta_range}). {info.quality_ru.capitalize()}. {status}."
            )
        )

    def _toggle_models_info(self) -> None:
        self._models_info_expanded = not self._models_info_expanded
        if self._models_info_expanded:
            self.models_toggle_btn.configure(text="Скрыть сведения о моделях")
            self.models_legend.grid(row=6, column=1, columnspan=2, sticky="w", pady=(0, 6))
        else:
            self.models_toggle_btn.configure(text="Больше о моделях")
            self.models_legend.grid_remove()

    def _persist_form_settings(self) -> None:
        self.settings.output_dir = self.output_var.get().strip() or self.settings.output_dir
        self.settings.model_size = self._selected_model()
        self.settings.write_srt = False
        self.settings.notify_on_complete = bool(self.notify_var.get())
        self.settings.language = "ru"
        self.settings.save()

    def _notify_completion(self, title: str, body: str) -> None:
        if not self.settings.notify_on_complete:
            return
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass
        try:
            safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
            safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{safe_body}" with title "{safe_title}"',
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            pass
        messagebox.showinfo(title, body, parent=self)

    def _set_busy(self, busy: bool) -> None:
        ready = check_dependencies().ready
        if busy:
            self.start_btn.configure(state="disabled")
            self.install_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
            self.save_as_btn.configure(state="disabled")
        else:
            self.start_btn.configure(state="normal" if ready else "disabled")
            self.install_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self.save_as_btn.configure(state="normal" if self._result_ready else "disabled")

    def _set_preview(self, text: str, *, result_ready: bool | None = None) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")
        if result_ready is not None:
            self._result_ready = result_ready
            if result_ready:
                self._last_result_text = text
        self.copy_btn.configure(
            state="normal" if self._result_ready else "disabled",
            text=_COPY_BTN_LABEL,
            image=self._copy_icon,
        )
        self.save_as_btn.configure(state="normal" if self._result_ready else "disabled")

    def _copy_result(self) -> None:
        if not self._result_ready:
            return
        text = self.preview.get("1.0", "end-1c")
        if not text.strip():
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except Exception as exc:
            messagebox.showerror("Буфер обмена", f"Не удалось скопировать:\n{exc}", parent=self)
            return
        self.copy_btn.configure(text=_COPIED_BTN_LABEL, image=self._copied_icon)

        def _restore() -> None:
            if self.winfo_exists():
                self.copy_btn.configure(text=_COPY_BTN_LABEL, image=self._copy_icon)

        self.after(1800, _restore)

    def _save_as(self) -> None:
        if not self._result_ready:
            return
        text = self._last_result_text or self.preview.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("Сохранить как", "Нет текста для сохранения.", parent=self)
            return

        initial_dir = self.output_var.get().strip() or self.settings.output_dir
        path_str = filedialog.asksaveasfilename(
            title="Сохранить результат как",
            initialdir=initial_dir or None,
            initialfile=f"{self._last_result_stem}.txt",
            defaultextension=".txt",
            filetypes=SAVE_AS_FILETYPES,
        )
        if not path_str:
            return

        path = Path(path_str)
        if not path.suffix:
            # macOS иногда не подставляет расширение — берём .txt
            path = path.with_suffix(".txt")

        try:
            written = write_export(path, text)
        except OSError as exc:
            messagebox.showerror("Сохранить как", f"Не удалось сохранить файл:\n{exc}", parent=self)
            return

        messagebox.showinfo("Сохранено", f"Файл записан:\n{written}", parent=self)

    def _on_progress(self, update: ProgressUpdate) -> None:
        def apply() -> None:
            self.progress.set(max(0.0, min(update.percent, 100.0)) / 100.0)
            self.pct_label.configure(text=f"{update.percent:.0f}%")
            self.stage_label.configure(text=update.message)
            self.speed_label.configure(text=f"Скорость: {_fmt_speed(update.speed_x)}")
            self.eta_label.configure(text=f"Осталось: {_fmt_eta(update.eta_sec)}")

        self.after(0, apply)

    def _install_deps(self) -> None:
        self._set_busy(True)
        self.stage_label.configure(text="Установка Whisper…")
        self.progress.set(0.05)
        self._set_preview(
            "Устанавливаем Whisper и необходимые компоненты.\n"
            "Это бесплатно. Подождите — прогресс отображается выше.\n"
        )

        def work() -> None:
            try:
                def cb(msg: str, frac: float) -> None:
                    self._on_progress(
                        ProgressUpdate(stage="install", percent=frac * 100, message=msg)
                    )

                status = ensure_dependencies(on_progress=cb, install_ffmpeg=True)
                self.after(0, lambda: self._apply_deps_status(status))
                if status.ready:
                    self.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Установка завершена",
                            "Whisper установлен и готов к работе.\n\n"
                            "При первой транскрибации один раз скачается выбранная модель.",
                        ),
                    )
                    self.after(
                        0,
                        lambda: self._set_preview(
                            "Whisper установлен. Выберите файл и нажмите «Транскрибировать».\n"
                        ),
                    )
                else:
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            "Установка не завершена",
                            "Не удалось установить всё автоматически.\n\n"
                            + "\n".join(status.details),
                        ),
                    )
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Установка", str(exc)))
                self.after(0, lambda: self.stage_label.configure(text="Установка не удалась"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _start(self) -> None:
        if not self.source_path or not self.source_path.exists():
            messagebox.showwarning("Файл", "Сначала выберите видео или аудиофайл.")
            return

        self._persist_form_settings()
        out = Path(self.settings.output_dir).expanduser()
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Папка", f"Не удалось создать папку вывода:\n{exc}")
            return

        status = check_dependencies()
        if not status.ready:
            self._offer_install(status=status)
            return

        model_name = self._selected_model()
        if not is_model_cached(model_name):
            info = get_model_info(model_name)
            ok = messagebox.askyesno(
                "Скачивание модели Whisper",
                "Перед транскрибацией нужно один раз скачать модель.\n\n"
                f"Модель: {info.name}\n"
                f"Размер: {format_size_gb(info.size_gb)}\n"
                f"Среднее время ожидания: {format_avg_wait(info.avg_download_min)} "
                f"(обычно {info.eta_range} при ~50 Мбит/с)\n\n"
                f"{info.quality_ru.capitalize()}.\n\n"
                "Скачать сейчас и продолжить?",
            )
            if not ok:
                return

        self.cancel_event.clear()
        self._set_busy(True)
        self._set_preview("Идёт транскрибация…\n", result_ready=False)
        self.progress.set(0)
        settings_snapshot = AppSettings(
            output_dir=str(out),
            model_size=self.settings.model_size,
            language="ru",
            write_srt=False,
            notify_on_complete=self.settings.notify_on_complete,
            device=self.settings.device,
        )
        source = self.source_path

        def work() -> None:
            try:
                result = transcribe_media(
                    source=source,
                    output_dir=out,
                    settings=settings_snapshot,
                    on_progress=self._on_progress,
                    cancel_event=self.cancel_event,
                )

                def done() -> None:
                    self._last_result_stem = result.text_path.stem
                    self._set_preview(result.text, result_ready=True)
                    self.stage_label.configure(
                        text=f"Готово → {result.text_path.name} "
                        f"({result.duration_sec:.0f} с аудио за {result.wall_sec:.0f} с)"
                    )
                    body = f"Текст сохранён:\n{result.text_path}"
                    self._notify_completion("Транскрибация завершена", body)

                self.after(0, done)
            except TranscriptionCancelled:
                self.after(0, lambda: self.stage_label.configure(text="Отменено"))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Ошибка", str(exc)))
                self.after(0, lambda: self.stage_label.configure(text="Ошибка транскрибации"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.stage_label.configure(text="Отмена…")


def run() -> None:
    app = WhisperApp()
    app.mainloop()
