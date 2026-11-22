# Whisper Транскрибер (macOS)

Локальное приложение: **видео → читаемый русский текст** через [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Без облака, без лимита на размер файла, с прогрессом (скорость и оставшееся время).

## Что умеет

- Выбор видео/аудио и **папки вывода на каждую запись**
- Папка по умолчанию — **Рабочий стол**; последний путь запоминается
- Автопроверка и установка зависимостей (кнопка в UI или скрипт)
- Прогресс: процент, скорость (`×` realtime), оценка «сколько осталось»
- Результат с **пунктуацией и нормальными пробелами** (язык `ru`)
- Дополнительно: `.srt` субтитры и `.meta.json`

## Быстрый старт на Mac

```bash
cd whisper-transcriber
chmod +x scripts/run_mac.sh
./scripts/run_mac.sh
```

Или двойной клик по `scripts/Whisper Transcriber.command` (после `chmod +x`).

Первый запуск:

1. Создаст `.venv` и минимальные пакеты GUI
2. Откроет окно приложения
3. Если Whisper ещё не готов — покажет диалог: **зачем нужен Whisper, что это бесплатно**, и запросит подтверждение
4. После согласия приложение **само** установит Whisper (и ffmpeg при необходимости) — вручную ничего ставить не нужно

При первой транскрибации скачается модель Whisper (`medium` по умолчанию).

### Требования

- macOS + Python 3.10+
- [Homebrew](https://brew.sh) (удобно для `ffmpeg`)
- Место на диске под модель (medium ≈ 1.5 GB)

## Интерфейс

1. **Выбрать…** — видео или аудио  
2. **Куда…** — папка для `.txt` / `.srt` (по умолчанию Desktop)  
3. Модель: `tiny`…`large-v3` (для русского лучше `medium` или `large-v3`)  
4. **Транскрибировать** — следите за прогрессом и ETA  
5. Текст появится в окне и сохранится в выбранную папку  

Если Whisper ещё не установлен — **Установить Whisper**.

## CLI

```bash
./scripts/run_mac.sh --check
./scripts/run_mac.sh --install
./scripts/run_mac.sh --cli ~/Movies/lecture.mp4 -o ~/Desktop/Transcripts --model medium
```

## Как устроен пайплайн

1. `ffmpeg` извлекает моно-аудио 16 kHz (видео любого размера → дольше по времени)  
2. Whisper транскрибирует сегментами (`language=ru`, VAD)  
3. Постпроцесс: пробелы, знаки, заглавные после конца предложения  
4. Запись `имя.txt` (+ `имя.srt`) в указанную папку  

Настройки: `~/Library/Application Support/WhisperTranscriber/settings.json`

## Разработка

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py
```
