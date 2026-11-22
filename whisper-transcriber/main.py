#!/usr/bin/env python3
"""Точка входа Whisper Транскрибер (macOS / desktop)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    parser = argparse.ArgumentParser(description="Транскрибация видео в текст через Whisper")
    parser.add_argument("--cli", action="store_true", help="Запуск без GUI")
    parser.add_argument("source", nargs="?", help="Видео/аудио файл (для --cli)")
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Папка для результата (по умолчанию — из настроек / Рабочий стол)",
    )
    parser.add_argument("--model", default=None, help="Размер модели Whisper")
    parser.add_argument("--no-srt", action="store_true", help="Не писать .srt")
    parser.add_argument("--check", action="store_true", help="Проверить зависимости и выйти")
    parser.add_argument("--install", action="store_true", help="Установить зависимости и выйти")
    args = parser.parse_args(argv)

    from app.installer import check_dependencies, ensure_dependencies
    from app.settings import AppSettings

    if args.check:
        status = check_dependencies()
        print("\n".join(status.details))
        return 0 if status.ready else 1

    if args.install:
        status = ensure_dependencies(on_progress=lambda m, p: print(f"[{p:.0%}] {m}"))
        print("\n".join(status.details))
        return 0 if status.ready else 1

    if args.cli:
        if not args.source:
            parser.error("Для --cli укажите путь к файлу")
        settings = AppSettings.load()
        if args.output_dir:
            settings.output_dir = args.output_dir
        if args.model:
            settings.model_size = args.model
        if args.no_srt:
            settings.write_srt = False
        settings.language = "ru"
        settings.save()

        from app.engine import ProgressUpdate, transcribe_media

        def on_progress(u: ProgressUpdate) -> None:
            speed = f", {u.speed_x:.2f}×" if u.speed_x else ""
            eta = f", ETA {u.eta_sec:.0f}s" if u.eta_sec is not None else ""
            print(f"[{u.percent:5.1f}%] {u.message}{speed}{eta}", flush=True)

        result = transcribe_media(
            source=Path(args.source),
            output_dir=Path(settings.output_dir),
            settings=settings,
            on_progress=on_progress,
        )
        print(f"\nГотово: {result.text_path}")
        if result.srt_path:
            print(f"SRT: {result.srt_path}")
        return 0

    from app.gui import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())