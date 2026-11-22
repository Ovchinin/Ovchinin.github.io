from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .ffmpeg_tools import (
    count_audio_streams,
    find_ffmpeg,
    media_duration_sec,
    summarize_ffmpeg_error,
    wav_rms_level,
)
from .punctuation_ru import format_russian_transcript, segments_to_plain_text, segments_to_srt
from .models_info import download_status_message, is_model_cached, model_download_hint, models_dir
from .settings import AppSettings

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus"}


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


def _run_ffmpeg_extract(
    ffmpeg: str,
    cmd: list[str],
    dest_wav: Path,
    *,
    duration: float,
    on_progress: ProgressCallback | None,
    cancel_event: threading.Event | None,
) -> tuple[bool, str]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stderr is not None
    while True:
        if cancel_event and cancel_event.is_set():
            proc.kill()
            raise TranscriptionCancelled()
        ret = proc.poll()
        if ret is not None:
            err = proc.stderr.read()
            ok = ret == 0 and dest_wav.exists() and dest_wav.stat().st_size > 44
            return ok, err
        time.sleep(0.2)
        if on_progress and duration > 0:
            on_progress(
                ProgressUpdate(
                    stage="extract",
                    percent=8.0,
                    message="Извлечение и нормализация аудио…",
                    audio_total_sec=duration,
                )
            )


def extract_audio(
    source: Path,
    dest_wav: Path,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> float:
    """Извлечь моно-аудио 16 kHz с усилением (важно для записей экрана телефона)."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg не найден. Откройте установку компонентов в приложении ещё раз — "
            "ffmpeg скачается автоматически, Homebrew не нужен."
        )

    duration = media_duration_sec(source, ffmpeg)
    n_audio = count_audio_streams(source, ffmpeg)
    if on_progress:
        on_progress(
            ProgressUpdate(
                stage="extract",
                percent=2.0,
                message=(
                    "Извлечение аудиодорожки…"
                    + (f" (найдено дорожек: {n_audio})" if n_audio else " (поиск звука…)")
                ),
                audio_total_sec=duration or None,
            )
        )

    # Фильтры: записи экрана с телефона часто очень тихие → Whisper «ломается» на буквы
    filters = (
        "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=16000",
        "dynaudnorm=f=150:g=15,volume=2.5,aresample=16000",
        "volume=5.0,highpass=f=80,lowpass=f=8000,aresample=16000",
        "aresample=16000",
    )

    attempts: list[list[str]] = []
    if n_audio >= 2:
        # Смешать все аудидорожки (на телефонах бывает «микрофон + звук приложения»)
        inputs = "".join(f"[0:a:{i}]" for i in range(min(n_audio, 4)))
        n = min(n_audio, 4)
        for af in filters[:2]:
            attempts.append(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source),
                    "-filter_complex",
                    f"{inputs}amix=inputs={n}:duration=longest:dropout_transition=0,{af}[aout]",
                    "-map",
                    "[aout]",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(dest_wav),
                ]
            )
    for af in filters:
        attempts.append(
            [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0?",
                "-vn",
                "-sn",
                "-dn",
                "-af",
                af,
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(dest_wav),
            ]
        )
        attempts.append(
            [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-sn",
                "-dn",
                "-af",
                af,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(dest_wav),
            ]
        )

    last_err = ""
    best_path: Path | None = None
    best_rms = -1.0
    for cmd in attempts:
        ok, err = _run_ffmpeg_extract(
            ffmpeg,
            cmd,
            dest_wav,
            duration=duration,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
        if not ok:
            last_err = err
            continue
        rms = wav_rms_level(dest_wav)
        if rms > best_rms:
            best_rms = rms
            # сохраняем лучший вариант во временную копию
            best_path = dest_wav.with_suffix(".best.wav")
            shutil.copy2(dest_wav, best_path)
            # достаточно громко — можно остановиться
            if rms >= 0.02:
                break

    if best_path and best_path.exists():
        shutil.move(str(best_path), str(dest_wav))
        if on_progress:
            msg = "Аудио готово, загрузка модели Whisper…"
            if best_rms < 0.01:
                msg = "Аудио тихое (запись экрана?) — усилили. Загрузка модели…"
            on_progress(
                ProgressUpdate(
                    stage="extract",
                    percent=12.0,
                    message=msg,
                    audio_total_sec=duration or None,
                )
            )
        return duration or media_duration_sec(dest_wav, ffmpeg)

    detail = summarize_ffmpeg_error(last_err)
    if _looks_like_missing_audio(detail) or _looks_like_missing_audio(last_err):
        raise RuntimeError(
            "Не удалось найти звуковую дорожку, которую можно извлечь.\n\n"
            "Если в плеере звук есть, пришлите формат файла (например mp4/mov) — "
            "иногда запись экрана с телефона кладёт звук в нестандартный поток.\n"
            "Попробуйте экспортировать/пересохранить видео через «Файлы»/Галерею "
            "или сконвертировать в MP4 с AAC."
        )
    raise RuntimeError(f"Не удалось извлечь звук из файла.\n\n{detail}")


def _looks_like_missing_audio(text: str) -> bool:
    return bool(
        re.search(
            r"does not contain any stream|Output file does not contain|matches no streams",
            text or "",
            re.I,
        )
    )


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
    # На macOS int8 у ctranslate2 иногда «зависает» на загрузке — float32 надёжнее
    import sys

    if sys.platform == "darwin":
        return "float32"
    return "int8"


_model_lock = threading.Lock()
_model_cache: dict[tuple[str, str, str], object] = {}


def _start_heartbeat(
    on_progress: ProgressCallback | None,
    *,
    stage: str,
    percent: float,
    base_message: str,
    cancel_event: threading.Event | None = None,
    message_fn=None,
) -> tuple[threading.Event, threading.Thread | None]:
    stop = threading.Event()
    if on_progress is None:
        return stop, None

    def _beat() -> None:
        started = time.time()
        while not stop.wait(2.0):
            if cancel_event and cancel_event.is_set():
                break
            elapsed = int(time.time() - started)
            message = message_fn(elapsed) if message_fn else f"{base_message} ({elapsed} с)"
            on_progress(
                ProgressUpdate(
                    stage=stage,
                    percent=percent,
                    message=message,
                )
            )

    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    return stop, thread


def get_model(
    model_size: str,
    device: str,
    compute_type: str,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
):
    from faster_whisper import WhisperModel

    key = (model_size, device, compute_type)
    with _model_lock:
        cached = _model_cache.get(key)
        if cached is not None:
            return cached

        download_root = str(models_dir())
        cached_on_disk = is_model_cached(model_size)
        if on_progress:
            if cached_on_disk:
                on_progress(
                    ProgressUpdate(
                        stage="model",
                        percent=14.0,
                        message=f"Загрузка модели «{model_size}» с диска…",
                    )
                )
            else:
                on_progress(
                    ProgressUpdate(
                        stage="model",
                        percent=14.0,
                        message=model_download_hint(model_size) + " Скачивание…",
                    )
                )

        stop, _thread = _start_heartbeat(
            on_progress,
            stage="model",
            percent=14.0,
            base_message=f"Загрузка модели Whisper ({model_size})",
            cancel_event=cancel_event,
            message_fn=(
                None
                if cached_on_disk
                else (lambda elapsed: download_status_message(model_size, elapsed))
            ),
        )
        try:
            if cancel_event and cancel_event.is_set():
                raise TranscriptionCancelled()
            # Скачает веса при первом запуске в download_root (может занять несколько минут)
            model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root,
            )
        except TranscriptionCancelled:
            raise
        except Exception:
            # запасной compute_type, если выбранный не поддерживается
            if compute_type != "float32":
                if on_progress:
                    on_progress(
                        ProgressUpdate(
                            stage="model",
                            percent=14.0,
                            message=f"Повтор загрузки модели ({model_size}, float32)…",
                        )
                    )
                model = WhisperModel(
                    model_size,
                    device="cpu",
                    compute_type="float32",
                    download_root=download_root,
                )
                key = (model_size, "cpu", "float32")
            else:
                raise
        finally:
            stop.set()

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
    own_temp_audio = True

    try:
        if source.suffix.lower() in AUDIO_EXTENSIONS:
            # mp3/wav и т.п. — Whisper читает напрямую, без перекодировки в wav
            audio_path = source
            own_temp_audio = False
            duration = media_duration_sec(source)
            if on_progress:
                on_progress(
                    ProgressUpdate(
                        stage="extract",
                        percent=12.0,
                        message="Аудиофайл готов, подготовка модели…",
                        audio_total_sec=duration or None,
                    )
                )
        else:
            duration = extract_audio(source, audio_path, on_progress, cancel_event)

        device = _resolve_device(settings.device)
        compute_type = _resolve_compute_type(device)

        if on_progress:
            if is_model_cached(settings.model_size):
                model_msg = f"Загрузка модели «{settings.model_size}» с диска…"
            else:
                model_msg = model_download_hint(settings.model_size) + " Скачивание…"
            on_progress(
                ProgressUpdate(
                    stage="model",
                    percent=14.0,
                    message=model_msg,
                    audio_total_sec=duration or None,
                )
            )

        if cancel_event and cancel_event.is_set():
            raise TranscriptionCancelled()

        model = get_model(
            settings.model_size,
            device,
            compute_type,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )

        if on_progress:
            on_progress(
                ProgressUpdate(
                    stage="transcribe",
                    percent=16.0,
                    message="Транскрибация: анализ аудио (VAD)…",
                    audio_total_sec=duration or None,
                )
            )

        # VAD до первого сегмента тоже может идти долго — показываем «пульс»
        vad_stop, _vad_thread = _start_heartbeat(
            on_progress,
            stage="transcribe",
            percent=16.0,
            base_message="Транскрибация: подготовка аудио",
            cancel_event=cancel_event,
        )
        try:
            # Для тихих записей экрана с телефона VAD часто «съедает» речь,
            # а condition_on_previous_text даёт обрывки/отдельные буквы.
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=settings.language or "ru",
                task="transcribe",
                vad_filter=False,
                beam_size=3,
                best_of=3,
                temperature=0.0,
                condition_on_previous_text=False,
                word_timestamps=False,
                no_speech_threshold=0.5,
                compression_ratio_threshold=2.4,
            )
        finally:
            vad_stop.set()

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