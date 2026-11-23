#!/bin/sh
# PardusInsight için kullanıcı düzeyinde menü kısayolu oluşturur/kaldırır.
# Root gerektirmez; yalnızca ~/.local/share/applications altına yazar.
set -eu

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
TARGET="$TARGET_DIR/pardusinsight.desktop"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$TARGET"
    echo "Kaldırıldı: $TARGET"
    exit 0
fi

if [ -x "$APP_DIR/.venv/bin/python" ]; then
    PYTHON="$APP_DIR/.venv/bin/python"
else
    PYTHON="$(command -v python3)"
fi

mkdir -p "$TARGET_DIR"
cat > "$TARGET" <<EOF
[Desktop Entry]
Type=Application
Name=PardusInsight
GenericName=Sistem Kaynağı İzleyici
Comment=Salt-okunur kaynak izleme ve açıklanabilir darboğaz analizi
Path=$APP_DIR
Exec="$PYTHON" -m pardusinsight
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
EOF
echo "Oluşturuldu: $TARGET (Python: $PYTHON)"
