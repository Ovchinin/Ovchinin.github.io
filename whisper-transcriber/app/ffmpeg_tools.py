from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from .settings import app_support_dir


def bundled_bin_dir() -> Path:
    path = app_support_dir() / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_ffmpeg_path() -> Path:
    return bundled_bin_dir() / "ffmpeg"


def find_ffmpeg() -> str | None:
    """Системный ffmpeg, затем локальная копия приложения, затем imageio-ffmpeg."""
    which = shutil.which("ffmpeg")
    if which:
        return which

    bundled = bundled_ffmpeg_path()
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)

    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass

    return None


def _mac_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return "x86_64"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)


def _install_from_imageio() -> str:
    import imageio_ffmpeg

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not exe or not Path(exe).is_file():
        raise RuntimeError("imageio-ffmpeg не смог предоставить бинарник ffmpeg")

    target = bundled_ffmpeg_path()
    shutil.copy2(exe, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(target)


def _install_from_evermeet() -> str:
    """Запасной путь: статическая сборка ffmpeg для macOS."""
    # evermeet отдаёт zip с бинарником ffmpeg
    url = "https://evermeet.cx/ffmpeg/getrelease/zip"
    zip_path = bundled_bin_dir() / "ffmpeg-download.zip"
    _download(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        member = next((n for n in names if n.rstrip("/").endswith("ffmpeg")), None)
        if not member:
            raise RuntimeError("В архиве evermeet.cx не найден ffmpeg")
        zf.extract(member, bundled_bin_dir())
        extracted = bundled_bin_dir() / member
        target = bundled_ffmpeg_path()
        if extracted.resolve() != target.resolve():
            if target.exists():
                target.unlink()
            extracted.replace(target)
    zip_path.unlink(missing_ok=True)
    target = bundled_ffmpeg_path()
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(target)


def ensure_ffmpeg(on_progress=None) -> str:
    """Гарантировать наличие ffmpeg без Homebrew."""
    existing = find_ffmpeg()
    if existing:
        # Если нашли через imageio — продублируем в Application Support для стабильности
        bundled = bundled_ffmpeg_path()
        if not bundled.exists() and "imageio_ffmpeg" in existing.replace("\\", "/"):
            try:
                shutil.copy2(existing, bundled)
                bundled.chmod(bundled.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                return str(bundled)
            except OSError:
                return existing
        return existing

    if on_progress:
        on_progress("Скачивание ffmpeg (бесплатно, без Homebrew)…", 0.75)

    errors: list[str] = []
    try:
        return _install_from_imageio()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"imageio-ffmpeg: {exc}")

    if platform.system() == "Darwin":
        try:
            return _install_from_evermeet()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"evermeet.cx: {exc}")

    raise RuntimeError(
        "Не удалось автоматически скачать ffmpeg.\n"
        + "\n".join(errors)
        + f"\nАрхитектура: {_mac_arch()}"
    )


_AUDIO_STREAM_RE = re.compile(r"Stream #\d+:\d+(?:\([^)]*\))?: Audio:", re.IGNORECASE)
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _ffmpeg_probe_text(media: Path, ffmpeg: str | None = None) -> str:
    exe = ffmpeg or find_ffmpeg()
    if not exe:
        return ""
    proc = subprocess.run(
        [exe, "-hide_banner", "-i", str(media)],
        capture_output=True,
        text=True,
    )
    return (proc.stderr or "") + "\n" + (proc.stdout or "")


def media_duration_sec(media: Path, ffmpeg: str | None = None) -> float:
    """Длительность через ffmpeg -i (ffprobe не требуется)."""
    text = _ffmpeg_probe_text(media, ffmpeg)
    match = _DURATION_RE.search(text)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def has_audio_stream(media: Path, ffmpeg: str | None = None) -> bool:
    """Есть ли в файле хотя бы одна аудидорожка."""
    return _AUDIO_STREAM_RE.search(_ffmpeg_probe_text(media, ffmpeg)) is not None


def summarize_ffmpeg_error(stderr: str) -> str:
    """Вытащить суть ошибки ffmpeg, а не весь баннер сборки."""
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    interesting = [
        ln
        for ln in lines
        if re.search(
            r"error|does not contain any stream|invalid|failed|no such|permission|not found|unknown",
            ln,
            re.I,
        )
    ]
    if interesting:
        return "\n".join(interesting[-12:])
    return "\n".join(lines[-20:]) if lines else "неизвестная ошибка ffmpeg"
