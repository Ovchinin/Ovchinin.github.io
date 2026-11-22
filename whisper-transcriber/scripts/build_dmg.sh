#!/usr/bin/env bash
# Сборка Транскрибация.app + DMG (запускать на macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${ROOT}/dist"
APP_NAME="Транскрибация"
APP_DIR="${DIST}/${APP_NAME}.app"
DMG_PATH="${DIST}/${APP_NAME}.dmg"
STAGE="${DIST}/dmg-stage"

echo "→ Иконки"
python3 "${ROOT}/resources/generate_icon.py"

echo "→ Собираю ${APP_NAME}.app"
rm -rf "${APP_DIR}" "${STAGE}"
mkdir -p "${APP_DIR}/Contents/MacOS" "${APP_DIR}/Contents/Resources"

cp "${ROOT}/macos/Info.plist" "${APP_DIR}/Contents/Info.plist"
cp "${ROOT}/macos/Transkribaciya" "${APP_DIR}/Contents/MacOS/Transkribaciya"
chmod +x "${APP_DIR}/Contents/MacOS/Transkribaciya"

# Исходники приложения внутрь бандла
mkdir -p "${APP_DIR}/Contents/Resources/app_src"
rsync -a --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'dist' \
  --exclude '.git' \
  --exclude 'resources/AppIcon-ai-ref.png' \
  "${ROOT}/" "${APP_DIR}/Contents/Resources/app_src/"

# iconset → icns
ICONSET="${DIST}/AppIcon.iconset"
rm -rf "${ICONSET}"
mkdir -p "${ICONSET}"
cp "${ROOT}/resources/AppIcon-16.png"   "${ICONSET}/icon_16x16.png"
cp "${ROOT}/resources/AppIcon-32.png"   "${ICONSET}/diana.v@example.org"
cp "${ROOT}/resources/AppIcon-32.png"   "${ICONSET}/icon_32x32.png"
cp "${ROOT}/resources/AppIcon-64.png"   "${ICONSET}/ivan.p@example.net"
cp "${ROOT}/resources/AppIcon-128.png"  "${ICONSET}/icon_128x128.png"
cp "${ROOT}/resources/AppIcon-256.png"  "${ICONSET}/wendy.h@example.net"
cp "${ROOT}/resources/AppIcon-256.png"  "${ICONSET}/icon_256x256.png"
cp "${ROOT}/resources/AppIcon-512.png"  "${ICONSET}/wendy.h@example.net"
cp "${ROOT}/resources/AppIcon-512.png"  "${ICONSET}/icon_512x512.png"
cp "${ROOT}/resources/AppIcon-1024.png" "${ICONSET}/walt.e@example.net"
iconutil -c icns "${ICONSET}" -o "${APP_DIR}/Contents/Resources/AppIcon.icns"
rm -rf "${ICONSET}"

# Убрать карантин с локальной сборки
xattr -cr "${APP_DIR}" || true

echo "→ Собираю DMG"
mkdir -p "${STAGE}"
cp -R "${APP_DIR}" "${STAGE}/"
ln -s /Applications "${STAGE}/Applications"

# Фон-подсказка: перетащить в Applications (опционально без картинки)
rm -f "${DMG_PATH}"
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${STAGE}" \
  -ov -format UDZO \
  "${DMG_PATH}"

rm -rf "${STAGE}"
echo "Готово:"
echo "  ${APP_DIR}"
echo "  ${DMG_PATH}"
ls -lh "${DMG_PATH}"
