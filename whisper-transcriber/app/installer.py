from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


ProgressCallback = Callable[[str, float], None]


@dataclass
class DependencyStatus:
    python_ok: bool
    ffmpeg_ok: bool
    whisper_ok: bool
    ffmpeg_path: str | None
    details: list[str]

    @property
    def ready(self) -> bool:
        return self.python_ok and self.ffmpeg_ok and self.whisper_ok


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def check_dependencies() -> DependencyStatus:
    details: list[str] = []
    python_ok = sys.version_info >= (3, 9)
    if not python_ok:
        details.append(f"Нужен Python 3.9+, сейчас {sys.version.split()[0]}")
    else:
        details.append(f"Python {sys.version.split()[0]} — ок")

    ffmpeg_path = find_ffmpeg()
    ffmpeg_ok = ffmpeg_path is not None
    details.append(f"ffmpeg — {'найден: ' + ffmpeg_path if ffmpeg_ok else 'не найден'}")

    whisper_ok = _module_available("faster_whisper")
    details.append(f"faster-whisper — {'установлен' if whisper_ok else 'не установлен'}")

    return DependencyStatus(
        python_ok=python_ok,
        ffmpeg_ok=ffmpeg_ok,
        whisper_ok=whisper_ok,
        ffmpeg_path=ffmpeg_path,
        details=details,
    )


def _run(cmd: list[str], on_progress: ProgressCallback | None = None, label: str = "") -> None:
    if on_progress:
        on_progress(label or " ".join(cmd), 0.05)
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Команда не удалась: {' '.join(cmd)}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )


def install_ffmpeg_mac(on_progress: ProgressCallback | None = None) -> None:
    brew = shutil.which("brew")
    if not brew:
        raise RuntimeError(
            "Homebrew не найден. Установите с https://brew.sh и повторите, "
            "либо выполните вручную: brew install ffmpeg"
        )
    if on_progress:
        on_progress("Установка ffmpeg через Homebrew…", 0.2)
    _run([brew, "install", "ffmpeg"], on_progress, "Установка ffmpeg…")


def install_python_packages(on_progress: ProgressCallback | None = None) -> None:
    req = os.path.join(os.path.dirname(os.path.dirname(__file__)), "requirements.txt")
    if on_progress:
        on_progress("Установка Python-пакетов (faster-whisper)…", 0.4)
    _run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        on_progress,
        "Обновление pip…",
    )
    _run(
        [sys.executable, "-m", "pip", "install", "-r", req],
        on_progress,
        "Установка faster-whisper и GUI…",
    )
    if on_progress:
        on_progress("Пакеты установлены", 0.9)


def ensure_dependencies(
    on_progress: ProgressCallback | None = None,
    install_ffmpeg: bool = True,
) -> DependencyStatus:
    status = check_dependencies()
    if status.ready:
        if on_progress:
            on_progress("Все зависимости уже установлены", 1.0)
        return status

    if not status.python_ok:
        raise RuntimeError("Обновите Python до 3.9 или новее.")

    if not status.whisper_ok:
        install_python_packages(on_progress)

    status = check_dependencies()
    if not status.ffmpeg_ok and install_ffmpeg:
        if os.uname().sysname == "Darwin":
            install_ffmpeg_mac(on_progress)
        else:
            raise RuntimeError(
                "ffmpeg не найден. Установите его (на Mac: brew install ffmpeg) и перезапустите."
            )

    status = check_dependencies()
    if on_progress:
        on_progress("Готово" if status.ready else "Есть незакрытые зависимости", 1.0)
    return status