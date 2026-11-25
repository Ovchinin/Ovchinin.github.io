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

# Минимально для старта GUI; Whisper/ffmpeg приложение поставит само после согласия
python -m pip install --upgrade pip >/dev/null
python -m pip install "customtkinter>=5.2.2" "Pillow>=10.0.0" >/dev/null

echo "→ Открываю приложение. Если Whisper ещё не установлен — оно само предложит бесплатную установку."
exec python main.py "$@"