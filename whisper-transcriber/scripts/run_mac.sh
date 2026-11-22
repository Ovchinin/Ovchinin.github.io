#!/usr/bin/env bash
# Первый запуск на Mac: создаёт venv, ставит зависимости, открывает приложение.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "Не найден python3. Установите Python 3.10+ с https://www.python.org/downloads/"
    exit 1
  fi
fi

if [[ ! -d .venv ]]; then
  echo "→ Создаю виртуальное окружение…"
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "→ Устанавливаю ffmpeg через Homebrew…"
    brew install ffmpeg
  else
    echo "⚠ ffmpeg не найден. Установите Homebrew (https://brew.sh), затем: brew install ffmpeg"
    echo "  Приложение всё равно откроется — можно нажать «Установить Whisper» в UI."
  fi
fi

exec python main.py "$@"