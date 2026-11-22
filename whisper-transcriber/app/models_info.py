from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .settings import app_support_dir


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size_gb: float
    # Среднее время скачивания при ~50 Мбит/с (типичный домашний интернет)
    avg_download_min: float
    # Диапазон для подсказки
    eta_range: str
    quality_ru: str


# Размеры Systran/faster-whisper-* (CT2), округлённо
MODEL_INFO: dict[str, ModelInfo] = {
    "tiny": ModelInfo("tiny", 0.08, 0.3, "15–40 с", "быстро, менее точно"),
    "base": ModelInfo("base", 0.15, 0.5, "30–60 с", "быстро"),
    "small": ModelInfo("small", 0.5, 1.5, "1–3 мин", "хороший баланс"),
    "medium": ModelInfo("medium", 1.5, 4.0, "3–8 мин", "точнее, дольше"),
    "large-v3": ModelInfo("large-v3", 3.0, 8.0, "6–15 мин", "максимум качества"),
}


def get_model_info(name: str) -> ModelInfo:
    return MODEL_INFO.get(name, ModelInfo(name, 1.0, 3.0, "несколько минут", "неизвестно"))


def format_size_gb(size_gb: float) -> str:
    if size_gb < 0.1:
        return f"~{int(size_gb * 1000)} МБ"
    if size_gb < 1:
        return f"~{int(size_gb * 1000)} МБ"
    text = f"{size_gb:.1f}".rstrip("0").rstrip(".")
    return f"~{text} ГБ"


def model_download_hint(name: str) -> str:
    info = get_model_info(name)
    return (
        f"Модель «{info.name}»: {format_size_gb(info.size_gb)}, "
        f"среднее скачивание ≈ {info.avg_download_min:g} мин "
        f"(обычно {info.eta_range} на ~50 Мбит/с). {info.quality_ru}."
    )


def model_label_for_ui(name: str) -> str:
    info = get_model_info(name)
    return f"{info.name} — {format_size_gb(info.size_gb)}, ≈ {info.avg_download_min:g} мин"


def models_dir() -> Path:
    path = app_support_dir() / "whisper-models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_model_cached(name: str) -> bool:
    """Грубая проверка: есть ли локальные файлы модели faster-whisper."""
    root = models_dir()
    # WhisperModel кладёт в download_root/models--Systran--faster-whisper-<name> или snapshots
    patterns = [
        f"*{name}*",
        f"*faster-whisper-{name}*",
    ]
    for pattern in patterns:
        if any(root.glob(f"**/{pattern}")):
            # ищем хоть один бинарный/config файл существенного размера
            for path in root.glob(f"**/{pattern}"):
                if path.is_file() and path.stat().st_size > 1_000_000:
                    return True
                if path.is_dir():
                    for child in path.rglob("*"):
                        if child.is_file() and child.stat().st_size > 1_000_000:
                            return True
    return False


def download_status_message(name: str, elapsed_sec: int) -> str:
    info = get_model_info(name)
    avg_sec = max(int(info.avg_download_min * 60), 1)
    remaining = max(avg_sec - elapsed_sec, 0)
    return (
        f"Скачивание модели «{info.name}» ({format_size_gb(info.size_gb)})… "
        f"{elapsed_sec} с из ≈{avg_sec} с в среднем "
        f"(обычно {info.eta_range}; осталось ориентировочно ~{remaining} с)"
    )
