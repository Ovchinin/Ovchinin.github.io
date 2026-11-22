from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .ffmpeg_tools import find_ffmpeg, media_duration_sec
from .punctuation_ru import format_russian_transcript, segments_to_plain_text, segments_to_srt
from .settings import AppSettings


ProgressCallback = Callable[["ProgressUpdate"], None]


@dataclass
class ProgressUpdate:
    stage: str
    percent: float
    message: str
    speed_x: float | None = None  # сколько секунд аудио обрабатывается за 1 сек wall-clock
    eta_sec: float | None = None
    audio_processed_sec: float | None = None
    audio_total_sec: float | None = None


@dataclass
class TranscriptionResult:
    source: Path
    output_dir: Path
    text_path: Path
    srt_path: Path | None
    meta_path: Path
    text: str
    duration_sec: float
    wall_sec: float
    segments: list[dict] = field(default_factory=list)


class TranscriptionCancelled(Exception):
    pass


def extract_audio(
    source: Path,
    dest_wav: Path,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> float:
    """Извлечь моно-аудио 16 kHz. Размер видео не ограничивается."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg не найден. Откройте установку компонентов в приложении ещё раз — "
            "ffmpeg скачается автоматически, Homebrew не нужен."
        )

    duration = media_duration_sec(source, ffmpeg)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dest_wav),
    ]
    if on_progress:
        on_progress(
            ProgressUpdate(
                stage="extract",
                percent=2.0,
                message="Извлечение аудиодорожки…",
                audio_total_sec=duration or None,
            )
        )

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stderr is not None
    # ffmpeg пишет прогресс в stderr; для больших файлов просто ждём
    while True:
        if cancel_event and cancel_event.is_set():
            proc.kill()
            raise TranscriptionCancelled()
        ret = proc.poll()
        if ret is not None:
            err = proc.stderr.read()
            if ret != 0:
                raise RuntimeError(f"ffmpeg не смог извлечь аудио:\n{err[-3000:]}")
            break
        time.sleep(0.2)
        if on_progress and duration > 0:
            # Грубая оценка: пока идёт извлечение — держим 2–12%
            on_progress(
                ProgressUpdate(
                    stage="extract",
                    percent=8.0,
                    message="Извлечение аудиодорожки…",
                    audio_total_sec=duration,
                )
            )

    if on_progress:
        on_progress(
            ProgressUpdate(
                stage="extract",
                percent=12.0,
                message="Аудио готово, загрузка модели Whisper…",
                audio_total_sec=duration or None,
            )
        )
    return duration or media_duration_sec(dest_wav, ffmpeg)


def _resolve_device(preference: str) -> str:
    if preference and preference != "auto":
        return preference
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _resolve_compute_type(device: str) -> str:
    if device == "cuda":
        return "float16"
    # int8 на CPU обычно быстрее и экономит память на длинных файлах
    return "int8"


_model_lock = threading.Lock()
_model_cache: dict[tuple[str, str, str], object] = {}


def get_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    key = (model_size, device, compute_type)
    with _model_lock:
        cached = _model_cache.get(key)
        if cached is not None:
            return cached
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_cache[key] = model
        return model


def transcribe_media(
    source: Path,
    output_dir: Path,
    settings: AppSettings,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> TranscriptionResult:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise FileNotFoundError(f"Файл не найден: {source}")

    wall_start = time.time()
    tmp_dir = Path(tempfile.mkdtemp(prefix="whisper_tr_"))
    audio_path = tmp_dir / "audio.wav"

    try:
        duration = extract_audio(source, audio_path, on_progress, cancel_event)

        device = _resolve_device(settings.device)
        compute_type = _resolve_compute_type(device)

        if on_progress:
            on_progress(
                ProgressUpdate(
                    stage="model",
                    percent=14.0,
                    message=f"Загрузка модели Whisper ({settings.model_size})…",
                    audio_total_sec=duration or None,
                )
            )

        if cancel_event and cancel_event.is_set():
            raise TranscriptionCancelled()

        model = get_model(settings.model_size, device, compute_type)

        if on_progress:
            on_progress(
                ProgressUpdate(
                    stage="transcribe",
                    percent=16.0,
                    message="Транскрибация…",
                    audio_total_sec=duration or None,
                )
            )

        segments_iter, info = model.transcribe(
            str(audio_path),
            language=settings.language or "ru",
            task="transcribe",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            beam_size=5,
            best_of=5,
            # Пунктуация и регистр включены в модели по умолчанию
            condition_on_previous_text=True,
            word_timestamps=False,
        )

        total = float(getattr(info, "duration", None) or duration or 0.0)
        collected: list[dict] = []
        transcribe_start = time.time()

        for seg in segments_iter:
            if cancel_event and cancel_event.is_set():
                raise TranscriptionCancelled()

            item = {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": (seg.text or "").strip(),
            }
            collected.append(item)

            processed = item["end"]
            wall = max(time.time() - transcribe_start, 0.001)
            speed_x = processed / wall if processed > 0 else None
            remaining_audio = max(total - processed, 0.0)
            eta = (remaining_audio / speed_x) if speed_x and speed_x > 0 else None
            # 16% … 92% под транскрипцию
            pct = 16.0 + (processed / total) * 76.0 if total > 0 else 50.0

            if on_progress:
                on_progress(
                    ProgressUpdate(
                        stage="transcribe",
                        percent=min(pct, 92.0),
                        message=f"Транскрибация… {processed:.0f} / {total:.0f} с аудио",
                        speed_x=speed_x,
                        eta_sec=eta,
                        audio_processed_sec=processed,
                        audio_total_sec=total,
                    )
                )

        if on_progress:
            on_progress(
                ProgressUpdate(
                    stage="format",
                    percent=94.0,
                    message="Форматирование русского текста…",
                    audio_total_sec=total or None,
                    audio_processed_sec=total or None,
                )
            )

        plain = segments_to_plain_text(collected)
        plain = format_russian_transcript(plain, paragraph_breaks=False)

        stem = source.stem
        text_path = output_dir / f"{stem}.txt"
        text_path.write_text(plain, encoding="utf-8")

        srt_path = None
        if settings.write_srt:
            srt_path = output_dir / f"{stem}.srt"
            srt_path.write_text(segments_to_srt(collected), encoding="utf-8")

        wall_sec = time.time() - wall_start
        meta = {
            "source": str(source),
            "model": settings.model_size,
            "language": settings.language,
            "device": device,
            "duration_sec": total,
            "wall_sec": wall_sec,
            "segments": len(collected),
            "text_file": str(text_path),
            "srt_file": str(srt_path) if srt_path else None,
        }
        meta_path = output_dir / f"{stem}.meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if on_progress:
            on_progress(
                ProgressUpdate(
                    stage="done",
                    percent=100.0,
                    message="Готово",
                    speed_x=(total / wall_sec) if wall_sec > 0 and total else None,
                    eta_sec=0.0,
                    audio_processed_sec=total or None,
                    audio_total_sec=total or None,
                )
            )

        return TranscriptionResult(
            source=source,
            output_dir=output_dir,
            text_path=text_path,
            srt_path=srt_path,
            meta_path=meta_path,
            text=plain,
            duration_sec=total,
            wall_sec=wall_sec,
            segments=collected,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)