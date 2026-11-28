from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .settings import app_support_dir


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size_gb: float
    # Среднее время скачивания при ~50 Мбит/с (типичный домашний интернет), минуты
    avg_download_min: float
    # Диапазон для подсказки
    eta_range: str
    quality_ru: str


# Размеры Systran/faster-whisper-* (CT2), округлённо
MODEL_INFO: dict[str, ModelInfo] = {
    "tiny": ModelInfo("tiny", 0.075, 0.4, "15–40 с", "быстро, менее точно"),
    "base": ModelInfo("base", 0.15, 0.7, "30–60 с", "быстро"),
    "small": ModelInfo("small", 0.5, 1.5, "1–3 мин", "хороший баланс"),
    "medium": ModelInfo("medium", 1.5, 4.0, "3–8 мин", "точнее, дольше"),
    "large-v3": ModelInfo("large-v3", 3.0, 8.0, "6–15 мин", "максимум качества"),
}

MODEL_ORDER = ["tiny", "base", "small", "medium", "large-v3"]

HF_REPOS: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}


@dataclass
class InstalledModel:
    name: str
    revision: str
    remote_revision: str | None = None
    size_gb: float = 0.0

    @property
    def short_revision(self) -> str:
        return short_revision(self.revision)

    @property
    def short_remote(self) -> str:
        return short_revision(self.remote_revision or "")

    @property
    def update_available(self) -> bool:
        if not self.revision or not self.remote_revision:
            return False
        return self.revision != self.remote_revision


def get_model_info(name: str) -> ModelInfo:
    return MODEL_INFO.get(name, ModelInfo(name, 1.0, 3.0, "несколько минут", "неизвестно"))


def hf_repo_for(name: str) -> str:
    return HF_REPOS.get(name, f"Systran/faster-whisper-{name}")


def short_revision(rev: str) -> str:
    rev = (rev or "").strip()
    if not rev:
        return "—"
    return rev[:7]


def format_size_gb(size_gb: float) -> str:
    mb = size_gb * 1000
    if size_gb < 1:
        value = int(round(mb / 5.0) * 5) if mb >= 50 else int(round(mb))
        return f"~{value} МБ"
    text = f"{size_gb:.1f}".rstrip("0").rstrip(".")
    return f"~{text} ГБ"


def format_avg_wait(avg_download_min: float) -> str:
    """Человекочитаемое среднее время ожидания."""
    if avg_download_min < 1:
        seconds = max(15, int(round(avg_download_min * 60)))
        return f"≈ {seconds} с"
    if abs(avg_download_min - round(avg_download_min)) < 0.05:
        return f"≈ {int(round(avg_download_min))} мин"
    return f"≈ {avg_download_min:g} мин"


def model_download_hint(name: str) -> str:
    info = get_model_info(name)
    return (
        f"Модель «{info.name}»: {format_size_gb(info.size_gb)}, "
        f"среднее скачивание {format_avg_wait(info.avg_download_min)} "
        f"(обычно {info.eta_range} на ~50 Мбит/с). {info.quality_ru}."
    )


def model_label_for_ui(name: str) -> str:
    """Подпись в выпадающем списке: имя — вес, среднее время."""
    info = get_model_info(name)
    return (
        f"{info.name} — {format_size_gb(info.size_gb)}, "
        f"{format_avg_wait(info.avg_download_min)}"
    )


def all_models_legend() -> str:
    """Полный список подписей для всех моделей (для раскрывающегося блока)."""
    lines = ["Вес → среднее скачивание при ~50 Мбит/с:"]
    for name in MODEL_ORDER:
        info = get_model_info(name)
        lines.append(
            f"• {info.name}: {format_size_gb(info.size_gb)}, "
            f"{format_avg_wait(info.avg_download_min)} (обычно {info.eta_range}) — {info.quality_ru}"
        )
    return "\n".join(lines)


def models_dir() -> Path:
    path = app_support_dir() / "whisper-models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _registry_path() -> Path:
    return models_dir() / "installed.json"


def load_registry() -> dict[str, dict]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def save_registry(data: dict[str, dict]) -> None:
    path = _registry_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_installed_revision(name: str, revision: str, *, repo: str | None = None) -> None:
    if not name or not revision:
        return
    data = load_registry()
    data[name] = {
        "revision": revision,
        "repo": repo or hf_repo_for(name),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_registry(data)


def local_revision(name: str) -> str:
    entry = load_registry().get(name) or {}
    rev = str(entry.get("revision") or "").strip()
    if rev:
        return rev
    # Миграция: модель на диске без записи — помечаем как unknown до следующей загрузки
    if is_model_cached(name):
        return "unknown"
    return ""


def is_model_cached(name: str) -> bool:
    """Грубая проверка: есть ли локальные файлы модели faster-whisper."""
    root = models_dir()
    patterns = [
        f"*{name}*",
        f"*faster-whisper-{name}*",
    ]
    for pattern in patterns:
        if any(root.glob(f"**/{pattern}")):
            for path in root.glob(f"**/{pattern}"):
                if path.name == "installed.json":
                    continue
                if path.is_file() and path.stat().st_size > 1_000_000:
                    return True
                if path.is_dir():
                    for child in path.rglob("*"):
                        if child.is_file() and child.stat().st_size > 1_000_000:
                            return True
    return False


def list_installed_models() -> list[InstalledModel]:
    installed: list[InstalledModel] = []
    for name in MODEL_ORDER:
        if not is_model_cached(name) and name not in load_registry():
            continue
        if not is_model_cached(name):
            # запись в registry без файлов — убрать
            data = load_registry()
            if name in data:
                data.pop(name, None)
                save_registry(data)
            continue
        info = get_model_info(name)
        installed.append(
            InstalledModel(
                name=name,
                revision=local_revision(name),
                size_gb=info.size_gb,
            )
        )
    return installed


def model_paths_on_disk(name: str) -> list[Path]:
    root = models_dir()
    found: list[Path] = []
    needles = (name, f"faster-whisper-{name}")
    for path in root.iterdir() if root.exists() else []:
        if path.name == "installed.json":
            continue
        low = path.name.lower()
        if any(n.lower() in low for n in needles):
            found.append(path)
    # HF hub cache layout inside download_root
    for path in root.rglob("*"):
        if path == root or path.name == "installed.json":
            continue
        low = str(path).lower()
        if any(n.lower() in low for n in needles) and path not in found:
            # только верхнеуровневые каталоги snapshots/models--*
            if path.is_dir() and ("models--" in path.name or path.parent == root):
                found.append(path)
    # unique by resolve
    uniq: dict[str, Path] = {}
    for p in found:
        try:
            uniq[str(p.resolve())] = p
        except OSError:
            uniq[str(p)] = p
    return list(uniq.values())


def delete_model_files(name: str) -> None:
    for path in model_paths_on_disk(name):
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        except OSError:
            pass
    data = load_registry()
    data.pop(name, None)
    save_registry(data)


def fetch_remote_revision(name: str) -> str:
    """Текущий SHA модели на Hugging Face. Бросает исключение при сетевой ошибке."""
    from huggingface_hub import model_info

    info = model_info(hf_repo_for(name))
    sha = getattr(info, "sha", None) or ""
    if not sha:
        raise RuntimeError(f"Не удалось получить версию модели «{name}».")
    return str(sha)


def check_updates_for_installed() -> list[InstalledModel]:
    """Проверить обновления только для уже скачанных моделей."""
    installed = list_installed_models()
    if not installed:
        return []
    updated: list[InstalledModel] = []
    for item in installed:
        remote = fetch_remote_revision(item.name)
        item.remote_revision = remote
        # если локально unknown — считаем, что обновление есть (нужно зафиксировать)
        if item.revision in {"", "unknown"}:
            item.remote_revision = remote
        updated.append(item)
    return updated


def resolve_revision_after_download(name: str) -> str:
    """После скачивания зафиксировать remote SHA как локальную версию."""
    try:
        rev = fetch_remote_revision(name)
    except Exception:
        rev = f"local-{int(time.time())}"
    record_installed_revision(name, rev)
    return rev


def download_status_message(name: str, elapsed_sec: int) -> str:
    info = get_model_info(name)
    avg_sec = max(int(info.avg_download_min * 60), 1)
    remaining = max(avg_sec - elapsed_sec, 0)
    return (
        f"Скачивание модели «{info.name}» ({format_size_gb(info.size_gb)})… "
        f"{elapsed_sec} с из ≈{avg_sec} с в среднем "
        f"(обычно {info.eta_range}; осталось ориентировочно ~{remaining} с)"
    )
