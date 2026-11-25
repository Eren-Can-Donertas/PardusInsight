#!/bin/sh
# PardusInsight için kullanıcı düzeyinde menü kısayolu ve simge oluşturur/kaldırır.
# Root gerektirmez; yalnızca ~/.local/share altına yazar.
# Sistem geneline kurulum için Debian paketi: python3 scripts/build_deb.py
set -eu

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET_DIR="$DATA_HOME/applications"
TARGET="$TARGET_DIR/pardusinsight.desktop"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
ICON="$ICON_DIR/pardusinsight.svg"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$TARGET" "$ICON"
    echo "Kaldırıldı: $TARGET"
    exit 0
fi

if [ -x "$APP_DIR/.venv/bin/python" ]; then
    PYTHON="$APP_DIR/.venv/bin/python"
else
    PYTHON="$(command -v python3)"
fi

mkdir -p "$TARGET_DIR" "$ICON_DIR"
cp "$APP_DIR/packaging/pardusinsight.svg" "$ICON"
cat > "$TARGET" <<EOF
[Desktop Entry]
Type=Application
Name=PardusInsight
GenericName=Sistem Kaynağı İzleyici
Comment=Salt-okunur kaynak izleme ve açıklanabilir darboğaz analizi
Path=$APP_DIR
Exec="$PYTHON" -m pardusinsight
Icon=pardusinsight
Terminal=false
Categories=System;Monitor;
Keywords=cpu;ram;bellek;swap;disk;süreç;izleme;performans;darboğaz;
EOF
echo "Oluşturuldu: $TARGET (Python: $PYTHON)"
