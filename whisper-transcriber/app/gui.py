from __future__ import annotations

import threading
import time
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path

import customtkinter as ctk

from . import __version__
from .engine import ProgressUpdate, TranscriptionCancelled, transcribe_media
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


VIDEO_TYPES = [
    ("Видео / аудио", "*.mp4 *.mov *.m4v *.mkv *.avi *.webm *.mp3 *.m4a *.wav *.aac *.flac"),
    ("Все файлы", "*.*"),
]

MODEL_CHOICES = list(MODEL_ORDER)
MODEL_MENU_VALUES = [model_label_for_ui(name) for name in MODEL_CHOICES]


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
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title(f"Транскрибация {__version__}")
        self.geometry("820x720")
        self.minsize(720, 640)

        self.settings = AppSettings.load()
        self.source_path: Path | None = None
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._last_tick = time.time()

        self._build()
        self.after(200, self._bootstrap_deps)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkLabel(
            self,
            text="Транскрибация",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 4))

        sub = ctk.CTkLabel(
            self,
            text="Видео → текст · локально · Whisper · читаемый русский",
            text_color=("gray40", "gray65"),
        )
        sub.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 12))

        form = ctk.CTkFrame(self)
        form.grid(row=2, column=0, sticky="ew", padx=24, pady=8)
        form.grid_columnconfigure(1, weight=1)

        # Source
        ctk.CTkLabel(form, text="Файл").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        self.source_var = tk.StringVar(value="Файл не выбран")
        ctk.CTkEntry(form, textvariable=self.source_var, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(12, 6)
        )
        ctk.CTkButton(form, text="Выбрать…", width=110, command=self._pick_source).grid(
            row=0, column=2, padx=12, pady=(12, 6)
        )

        # Output dir
        ctk.CTkLabel(form, text="Папка").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.output_var = tk.StringVar(value=self.settings.output_dir)
        ctk.CTkEntry(form, textvariable=self.output_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=6
        )
        ctk.CTkButton(form, text="Куда…", width=110, command=self._pick_output).grid(
            row=1, column=2, padx=12, pady=6
        )

        # Model / language
        ctk.CTkLabel(form, text="Модель").grid(row=2, column=0, sticky="nw", padx=12, pady=6)
        initial_model = self.settings.model_size if self.settings.model_size in MODEL_CHOICES else "small"
        self.model_var = tk.StringVar(value=model_label_for_ui(initial_model))
        ctk.CTkOptionMenu(
            form,
            values=MODEL_MENU_VALUES,
            variable=self.model_var,
            width=280,
            command=lambda _v: self._refresh_model_hint(),
        ).grid(row=2, column=1, sticky="w", padx=8, pady=6)
        self.model_hint = ctk.CTkLabel(
            form,
            text="",
            text_color=("gray40", "gray65"),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.model_hint.grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 2))

        self.models_legend = ctk.CTkLabel(
            form,
            text=all_models_legend(),
            text_color=("gray35", "gray70"),
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self.models_legend.grid(row=4, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 6))
        self._refresh_model_hint()

        self.srt_var = tk.BooleanVar(value=self.settings.write_srt)
        ctk.CTkCheckBox(form, text="Также сохранить .srt (субтитры)", variable=self.srt_var).grid(
            row=5, column=1, sticky="w", padx=8, pady=(6, 12)
        )

        # Actions
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 14))
        actions.grid_columnconfigure(0, weight=1)

        self.deps_label = ctk.CTkLabel(actions, text="Проверка зависимостей…", anchor="w")
        self.deps_label.grid(row=0, column=0, sticky="w")

        self.install_btn = ctk.CTkButton(
            actions,
            text="Установить Whisper",
            width=160,
            command=self._offer_install,
        )
        self.install_btn.grid(row=0, column=1, padx=6)
        self.install_btn.grid_remove()

        self.start_btn = ctk.CTkButton(
            actions, text="Транскрибировать", width=160, command=self._start
        )
        self.start_btn.grid(row=0, column=2, padx=6)

        self.cancel_btn = ctk.CTkButton(
            actions,
            text="Отмена",
            width=100,
            fg_color=("gray70", "gray35"),
            command=self._cancel,
            state="disabled",
        )
        self.cancel_btn.grid(row=0, column=3, padx=(6, 0))

        # Progress + preview
        body = ctk.CTkFrame(self)
        body.grid(row=3, column=0, sticky="nsew", padx=24, pady=(8, 20))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)

        self.stage_label = ctk.CTkLabel(body, text="Ожидание файла", anchor="w")
        self.stage_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))

        self.progress = ctk.CTkProgressBar(body)
        self.progress.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        self.progress.set(0)

        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", padx=16, pady=4)
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1)

        self.pct_label = ctk.CTkLabel(stats, text="0%")
        self.pct_label.grid(row=0, column=0, sticky="w")
        self.speed_label = ctk.CTkLabel(stats, text="Скорость: —")
        self.speed_label.grid(row=0, column=1)
        self.eta_label = ctk.CTkLabel(stats, text="Осталось: —")
        self.eta_label.grid(row=0, column=2, sticky="e")

        self.preview = ctk.CTkTextbox(body, wrap="word")
        self.preview.grid(row=3, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self.preview.insert("1.0", "Здесь появится результат транскрибации.\n")
        self.preview.configure(state="disabled")

    def _bootstrap_deps(self) -> None:
        status = check_dependencies()
        self._apply_deps_status(status)
        if not status.ready:
            # Первый запуск / нет Whisper: объяснить, что это бесплатно, и спросить согласие
            self.after(100, lambda: self._offer_install(status=status, auto_prompt=True))

    def _apply_deps_status(self, status: DependencyStatus) -> None:
        if status.ready:
            self.deps_label.configure(text="Whisper и ffmpeg готовы к работе")
            self.install_btn.grid_remove()
            self.start_btn.configure(state="normal")
        else:
            missing = []
            if not status.whisper_ok:
                missing.append("Whisper")
            if not status.ffmpeg_ok:
                missing.append("ffmpeg")
            self.deps_label.configure(
                text="Для работы нужно установить: " + ", ".join(missing) + " (бесплатно)"
            )
            self.install_btn.grid()
            self.start_btn.configure(state="disabled")

    def _offer_install(
        self,
        status: DependencyStatus | None = None,
        auto_prompt: bool = False,
    ) -> None:
        """Показать согласие и при «Да» установить Whisper из приложения."""
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
            self.deps_label.configure(
                text="Установка отложена. Нажмите «Установить Whisper», когда будете готовы."
            )
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
        status = "уже скачана на диск" if cached else "будет скачана при первом запуске"
        self.model_hint.configure(
            text=(
                f"Выбрано «{info.name}»: {format_size_gb(info.size_gb)}, "
                f"среднее скачивание {format_avg_wait(info.avg_download_min)} "
                f"(обычно {info.eta_range}). {info.quality_ru.capitalize()}. "
                f"Сейчас: {status}."
            )
        )

    def _persist_form_settings(self) -> None:
        self.settings.output_dir = self.output_var.get().strip() or self.settings.output_dir
        self.settings.model_size = self._selected_model()
        self.settings.write_srt = bool(self.srt_var.get())
        self.settings.language = "ru"
        self.settings.save()

    def _set_busy(self, busy: bool) -> None:
        ready = check_dependencies().ready
        if busy:
            self.start_btn.configure(state="disabled")
            self.install_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
        else:
            self.start_btn.configure(state="normal" if ready else "disabled")
            self.install_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _on_progress(self, update: ProgressUpdate) -> None:
        def apply() -> None:
            self.progress.set(max(0.0, min(update.percent, 100.0)) / 100.0)
            self.pct_label.configure(text=f"{update.percent:.0f}%")
            self.stage_label.configure(text=update.message)
            self.speed_label.configure(text=f"Скорость: {_fmt_speed(update.speed_x)}")
            self.eta_label.configure(text=f"Осталось: {_fmt_eta(update.eta_sec)}")

        self.after(0, apply)

    def _install_deps(self) -> None:
        """Установка Whisper/ffmpeg из приложения после согласия пользователя."""
        self._set_busy(True)
        self.deps_label.configure(text="Идёт автоматическая установка…")
        self.stage_label.configure(text="Установка Whisper (бесплатно, из приложения)…")
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
                            "Whisper установлен из приложения и готов к работе.\n\n"
                            "Это бесплатно. При первой транскрибации один раз "
                            "скачается выбранная модель — размер и среднее время "
                            "скачивания показаны под списком моделей.",
                        ),
                    )
                    self.after(
                        0,
                        lambda: self._set_preview(
                            "Whisper установлен. Выберите видео и нажмите «Транскрибировать».\n"
                        ),
                    )
                else:
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            "Установка не завершена",
                            "Приложение не смогло установить всё автоматически.\n\n"
                            + "\n".join(status.details),
                        ),
                    )
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Установка", str(exc)))
                self.after(
                    0,
                    lambda: self.deps_label.configure(
                        text="Установка не удалась — нажмите «Установить Whisper» ещё раз"
                    ),
                )
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
        self._set_preview("Идёт транскрибация…\n")
        self.progress.set(0)
        settings_snapshot = AppSettings(
            output_dir=str(out),
            model_size=self.settings.model_size,
            language="ru",
            write_srt=self.settings.write_srt,
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
                    self._set_preview(result.text)
                    self.stage_label.configure(
                        text=f"Готово → {result.text_path.name} "
                        f"({result.duration_sec:.0f} с аудио за {result.wall_sec:.0f} с)"
                    )
                    messagebox.showinfo(
                        "Транскрибация завершена",
                        f"Текст сохранён:\n{result.text_path}"
                        + (f"\nСубтитры:\n{result.srt_path}" if result.srt_path else ""),
                    )

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