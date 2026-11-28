"""Панель «Установленные модели»: версии, проверка и обновление по запросу."""

from __future__ import annotations

import threading
import tkinter.messagebox as messagebox
from typing import Callable

import customtkinter as ctk

from .engine import clear_model_memory_cache, redownload_model
from .models_info import (
    InstalledModel,
    check_updates_for_installed,
    delete_model_files,
    format_size_gb,
    list_installed_models,
)
from .theme import COLOR, PRIMARY_BTN, SECONDARY_BTN, F, apply_appearance


class ModelsPanel(ctk.CTkToplevel):
    def __init__(
        self,
        master: ctk.CTk,
        *,
        current_model: str,
        on_models_changed: Callable[[], None] | None = None,
        on_background_status: Callable[[str | None], None] | None = None,
    ) -> None:
        super().__init__(master)
        apply_appearance()
        self.configure(fg_color=COLOR["bg"])
        self.title("Установленные модели")
        self.geometry("560x480")
        self.minsize(520, 420)
        self.transient(master)
        self.grab_set()

        self._current_model = current_model
        self._on_models_changed = on_models_changed
        self._on_background_status = on_background_status
        self._items: list[InstalledModel] = []
        self._checked = False
        self._busy = False
        self._row_frames: list[ctk.CTkFrame] = []

        pad = {"padx": 24}

        ctk.CTkLabel(
            self,
            text="Установленные модели",
            font=F(22),
            text_color=COLOR["ink"],
            anchor="w",
        ).pack(anchor="w", pady=(22, 12), **pad)

        self.list_host = ctk.CTkScrollableFrame(
            self,
            fg_color=COLOR["surface"],
            border_width=1,
            border_color=COLOR["line"],
            corner_radius=12,
        )
        self.list_host.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        self.empty_label = ctk.CTkLabel(
            self.list_host,
            text="Пока нет скачанных моделей.\nОни появятся после первой транскрибации.",
            font=F(13),
            text_color=COLOR["muted"],
            justify="left",
            anchor="w",
        )

        self.action_btn = ctk.CTkButton(
            self,
            text="Проверить обновления",
            height=40,
            font=F(14),
            command=self._on_primary_action,
            **SECONDARY_BTN,
        )
        self.action_btn.pack(fill="x", padx=24, pady=(0, 20))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(10, self._reload_list)

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.action_btn.configure(state=state)

    def _reload_list(self) -> None:
        for child in list(self.list_host.winfo_children()):
            child.destroy()
        self._row_frames.clear()

        if self._checked:
            items = self._items
        else:
            items = list_installed_models()
            self._items = items

        if not items:
            self.empty_label = ctk.CTkLabel(
                self.list_host,
                text="Пока нет скачанных моделей.\nОни появятся после первой транскрибации.",
                font=F(13),
                text_color=COLOR["muted"],
                justify="left",
                anchor="w",
            )
            self.empty_label.pack(anchor="w", padx=14, pady=16)
            self.action_btn.configure(text="Проверить обновления", **SECONDARY_BTN)
            return

        for item in items:
            self._add_row(item)

        if self._checked and any(i.update_available or i.revision in {"", "unknown"} for i in items):
            self.action_btn.configure(text="Скачать и обновить все", **PRIMARY_BTN)
        else:
            self.action_btn.configure(text="Проверить обновления", **SECONDARY_BTN)

    def _add_row(self, item: InstalledModel) -> None:
        row = ctk.CTkFrame(self.list_host, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)
        row.grid_columnconfigure(0, weight=1)

        title = ctk.CTkFrame(row, fg_color="transparent")
        title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title,
            text=item.name,
            font=F(15),
            text_color=COLOR["ink"],
            anchor="w",
        ).pack(side="left")
        if item.name == self._current_model:
            ctk.CTkLabel(
                title,
                text="  текущая  ",
                font=F(11),
                text_color=COLOR["ink"],
                fg_color=COLOR["bg"],
                corner_radius=10,
                height=22,
            ).pack(side="left", padx=(10, 0))

        if self._checked:
            if item.update_available or item.revision in {"", "unknown"}:
                remote = item.short_remote if item.remote_revision else "—"
                meta = f"{item.short_revision} → {remote} · есть обновление"
            else:
                meta = f"{item.short_revision} · актуальна"
        else:
            meta = f"версия {item.short_revision} · {format_size_gb(item.size_gb)}"

        ctk.CTkLabel(
            row,
            text=meta,
            font=F(12),
            text_color=COLOR["muted"],
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))

        if self._checked and (item.update_available or item.revision in {"", "unknown"}):
            ctk.CTkButton(
                actions,
                text="↓",
                width=36,
                height=36,
                font=F(16),
                command=lambda n=item.name: self._confirm_and_update([n]),
                **PRIMARY_BTN,
            ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            actions,
            text="⌫",
            width=36,
            height=36,
            font=F(14),
            command=lambda n=item.name: self._delete_model(n),
            **SECONDARY_BTN,
        ).pack(side="left")

        self._row_frames.append(row)

    def _on_primary_action(self) -> None:
        if self._busy:
            return
        if self._checked and any(i.update_available or i.revision in {"", "unknown"} for i in self._items):
            names = [
                i.name
                for i in self._items
                if i.update_available or i.revision in {"", "unknown"}
            ]
            self._confirm_and_update(names)
        else:
            self._check_updates()

    def _check_updates(self) -> None:
        if not list_installed_models():
            messagebox.showinfo(
                "Установленные модели",
                "Нет скачанных моделей для проверки.",
                parent=self,
            )
            return

        self._set_busy(True)
        self.action_btn.configure(text="Проверка…")

        def work() -> None:
            try:
                items = check_updates_for_installed()
            except Exception:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Нет подключения",
                        "Нет подключения к интернету. Не удалось проверить обновления.",
                        parent=self,
                    ),
                )
                self.after(0, lambda: self._finish_check(None))
                return
            self.after(0, lambda: self._finish_check(items))

        threading.Thread(target=work, daemon=True).start()

    def _finish_check(self, items: list[InstalledModel] | None) -> None:
        self._set_busy(False)
        if items is None:
            self.action_btn.configure(text="Проверить обновления", **SECONDARY_BTN)
            return
        self._checked = True
        self._items = items
        outdated = [i for i in items if i.update_available or i.revision in {"", "unknown"}]
        self._reload_list()
        if not outdated:
            messagebox.showinfo(
                "Обновления моделей",
                "Обновление не требуется. Установлены последние версии моделей.",
                parent=self,
            )
            # Сбрасываем режим «после проверки», чтобы при следующем открытии снова жали проверку
            self._checked = False
            self._reload_list()

    def _confirm_and_update(self, names: list[str]) -> None:
        if not names or self._busy:
            return
        size = sum(
            next((i.size_gb for i in self._items if i.name == n), 0.5) for n in names
        )
        names_line = ", ".join(names)
        ok = messagebox.askokcancel(
            "Обновить модели?",
            "Будут заменены файлы на диске для:\n"
            f"{names_line}\n\n"
            f"Размер загрузки ≈ {format_size_gb(size)}.\n"
            "Идущая транскрибация будет недоступна на время обновления.",
            parent=self,
        )
        if not ok:
            return
        self._start_updates(names)

    def _start_updates(self, names: list[str]) -> None:
        self._set_busy(True)
        if self._on_background_status:
            self._on_background_status("обновление…")

        def work() -> None:
            errors: list[str] = []
            for idx, name in enumerate(names):
                def progress(update, model_name=name, i=idx, total=len(names)) -> None:
                    msg = getattr(update, "message", "") or f"Обновление «{model_name}»…"
                    self.after(
                        0,
                        lambda m=msg, i=i, t=total: self.action_btn.configure(
                            text=f"Обновление {i + 1}/{t}: {m[:42]}"
                        ),
                    )
                    if self._on_background_status:
                        self.after(
                            0,
                            lambda m=msg: self._on_background_status(f"обновление… {m[:28]}"),
                        )

                try:
                    redownload_model(name, on_progress=progress)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {exc}")

            def done() -> None:
                self._set_busy(False)
                self._checked = False
                self._items = list_installed_models()
                self._reload_list()
                if self._on_background_status:
                    self._on_background_status(None)
                if self._on_models_changed:
                    self._on_models_changed()
                if errors:
                    messagebox.showerror(
                        "Обновление моделей",
                        "Не удалось скачать обновление. Проверьте подключение к сети.\n\n"
                        + "\n".join(errors[:4]),
                        parent=self,
                    )
                else:
                    messagebox.showinfo(
                        "Обновление моделей",
                        "Модели обновлены.",
                        parent=self,
                    )

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _delete_model(self, name: str) -> None:
        if self._busy:
            return
        ok = messagebox.askokcancel(
            "Удалить модель?",
            f"Удалить локальные файлы модели «{name}» с диска?",
            parent=self,
        )
        if not ok:
            return
        clear_model_memory_cache(name)
        delete_model_files(name)
        self._checked = False
        self._items = list_installed_models()
        self._reload_list()
        if self._on_models_changed:
            self._on_models_changed()
