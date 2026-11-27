#!/bin/sh
# technical_report.html -> technical_report.pdf (Google Chrome / Chromium, başsız mod).
# Geçici bir tarayıcı profili kullanılır; kişisel tarayıcı profiline dokunulmaz ve
# rapor harici kaynak yüklemez.
set -eu
DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$DIR")
CHROME=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)}
if [ -z "$CHROME" ]; then
    echo "Chrome/Chromium bulunamadı; CHROME=/yol/tarayici ile belirtin." >&2
    exit 1
fi
PROFILE=$(mktemp -d)
trap 'rm -rf "$PROFILE"' EXIT
"$CHROME" --headless=new --disable-gpu --no-first-run --no-default-browser-check \
    --disable-background-networking --disable-component-update --disable-sync \
    --disable-extensions --user-data-dir="$PROFILE" --no-pdf-header-footer \
    --print-to-pdf="$ROOT/technical_report.pdf" "file://$DIR/technical_report.html"
echo "Oluşturuldu: $ROOT/technical_report.pdf"
