from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

from .ffmpeg_tools import ensure_ffmpeg, find_ffmpeg


ProgressCallback = Callable[[str, float], None]

# faster-whisper → onnxruntime: колёс для 3.14 пока нет
MIN_PY = (3, 10)
MAX_PY = (3, 13)


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


def python_supported(info: tuple[int, int] | None = None) -> bool:
    major_minor = info or sys.version_info[:2]
    return MIN_PY <= major_minor <= MAX_PY


def python_requirement_message() -> str:
    current = sys.version.split()[0]
    return (
        f"Для Whisper нужен Python 3.10–3.13 (лучше 3.12). Сейчас: {current}.\n\n"
        "Python 3.14 пока не поддерживается: нет пакета onnxruntime.\n\n"
        "Установите Python 3.12 с https://www.python.org/downloads/macos/\n"
        "затем полностью закройте «Транскрибация» и откройте снова — "
        "окружение пересоздастся автоматически."
    )


def check_dependencies() -> DependencyStatus:
    details: list[str] = []
    python_ok = python_supported()
    if not python_ok:
        details.append(python_requirement_message().split("\n")[0])
    else:
        details.append(f"Python {sys.version.split()[0]} — ок")

    ffmpeg_path = find_ffmpeg()
    ffmpeg_ok = ffmpeg_path is not None
    details.append(f"ffmpeg — {'найден: ' + ffmpeg_path if ffmpeg_ok else 'будет скачан приложением'}")

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
        err = (proc.stderr or "") + "\n" + (proc.stdout or "")
        if "onnxruntime" in err.lower() and not python_supported():
            raise RuntimeError(python_requirement_message())
        if "onnxruntime" in err.lower():
            raise RuntimeError(
                "Не удалось установить onnxruntime (нужен для Whisper).\n\n"
                "Чаще всего помогает Python 3.12 вместо 3.14.\n"
                "Установите 3.12 с https://www.python.org/downloads/macos/ "
                "и перезапустите приложение.\n\n"
                f"Детали:\n{err[-2500:]}"
            )
        raise RuntimeError(
            f"Команда не удалась: {' '.join(cmd)}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )


def install_python_packages(on_progress: ProgressCallback | None = None) -> None:
    if not python_supported():
        raise RuntimeError(python_requirement_message())

    req = os.path.join(os.path.dirname(os.path.dirname(__file__)), "requirements.txt")
    if on_progress:
        on_progress("Установка Python-пакетов (Whisper и ffmpeg)…", 0.35)
    _run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        on_progress,
        "Обновление pip…",
    )
    _run(
        [sys.executable, "-m", "pip", "install", "-r", req],
        on_progress,
        "Установка Whisper и компонентов…",
    )
    if on_progress:
        on_progress("Пакеты установлены", 0.7)


def ensure_dependencies(
    on_progress: ProgressCallback | None = None,
    install_ffmpeg: bool = True,
) -> DependencyStatus:
    """Установить всё из приложения: Whisper + ffmpeg. Homebrew не нужен."""
    status = check_dependencies()
    if status.ready:
        if on_progress:
            on_progress("Все зависимости уже установлены", 1.0)
        return status

    if not status.python_ok:
        raise RuntimeError(python_requirement_message())

    if not status.whisper_ok or not _module_available("imageio_ffmpeg"):
        install_python_packages(on_progress)

    if install_ffmpeg:
        ensure_ffmpeg(on_progress=on_progress)

    status = check_dependencies()
    if on_progress:
        on_progress("Готово" if status.ready else "Есть незакрытые зависимости", 1.0)
    return status
