from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def _default_desktop() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        return desktop
    # Fallback for non-macOS / localized Desktop names during development
    return Path.home()


def app_support_dir() -> Path:
    if sys_platform_is_mac():
        base = Path.home() / "Library" / "Application Support" / "Транскрибация"
    else:
        base = Path.home() / ".config" / "transkribaciya"
    base.mkdir(parents=True, exist_ok=True)
    return base


def sys_platform_is_mac() -> bool:
    return os.uname().sysname == "Darwin"


@dataclass
class AppSettings:
    output_dir: str = ""
    model_size: str = "small"
    language: str = "ru"
    write_srt: bool = False  # субтитры .srt больше не сохраняются из GUI
    notify_on_complete: bool = True
    device: str = "auto"  # auto | cpu | cuda

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = str(_default_desktop())

    @classmethod
    def load(cls) -> "AppSettings":
        path = app_support_dir() / "settings.json"
        if not path.exists():
            settings = cls()
            settings.save()
            return settings
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self) -> None:
        path = app_support_dir() / "settings.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    def output_path(self) -> Path:
        path = Path(self.output_dir).expanduser()
        if not path.exists():
            path = _default_desktop()
            self.output_dir = str(path)
            self.save()
        return path