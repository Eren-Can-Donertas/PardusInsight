#!/bin/sh
# PardusInsight — Pardus 25.1 XFCE doğrulama betiği (PARDUS_VALIDATION.md'nin otomatik kısmı).
#
# Hiçbir paket kurmaz, sistem ayarı değiştirmez, root gerektirmez. Yalnızca ölçüm yapar ve
# çıktıları verilen klasöre yazar. Pardus'ta XFCE oturumu açık bir standart kullanıcıyla:
#
#     sh scripts/pardus_validate.sh                 # ./pardus_dogrulama_<tarih>/ altına yazar
#     sh scripts/pardus_validate.sh ~/sonuclar      # belirtilen klasöre yazar
#
# Sanal ortam kullanıyorsanız: PYTHON=.venv/bin/python sh scripts/pardus_validate.sh
set -u

APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-"$APP_DIR/pardus_dogrulama_$(date +%Y%m%d_%H%M%S)"}
PY=${PYTHON:-python3}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$APP_DIR" || exit 1

log() { printf '%s\n' "$*" | tee -a "$OUT/ozet.txt"; }

run() {
    name=$1
    shift
    log "## $name"
    log "\$ $*"
    "$@" > "$OUT/$name.log" 2>&1
    code=$?
    tail -n 6 "$OUT/$name.log" | tee -a "$OUT/ozet.txt"
    log "çıkış kodu: $code"
    log ""
}

log "# PardusInsight Pardus doğrulaması — $(date -Iseconds)"
log "Uygulama dizini: $APP_DIR · Python: $PY"
log ""

run ortam sh -c 'cat /etc/os-release; echo; uname -a; echo; id; \
    echo "XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-} XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-}"; \
    nproc; free -m; echo "PSI:"; ls /proc/pressure 2>&1'
run paketler apt-cache policy python3 python3-psutil python3-pyside6.qtwidgets \
    python3-pytest libxcb-cursor0
run python_surumleri "$PY" -c 'import sys, psutil, PySide6; print(sys.version); \
print("psutil", psutil.__version__); print("PySide6", PySide6.__version__)'
run standart_kullanici sh -c 'if [ "$(id -u)" -ne 0 ]; then echo "standart kullanıcı: $(id -un)"; \
    else echo "UYARI: root ile çalıştırılıyor; doğrulama standart kullanıcıyla yapılmalı"; exit 1; fi'
run testler "$PY" -m pytest -q -p no:cacheprovider
run olcum_dogrulama "$PY" scripts/validate_metrics.py --rounds 10 --interval 1
run canli_headless_60sn "$PY" -m pardusinsight --headless --duration 60 --quiet \
    --export-json "$OUT/canli_60sn.json" --export-csv "$OUT/canli_60sn.csv"
run demo_kayit_analizi "$PY" -m pardusinsight --headless --replay scenarios/demo.json
run performans_headless "$PY" scripts/perf_check.py --duration 60

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    run performans_gui "$PY" scripts/perf_check.py --gui --duration 60
    run ekran_goruntuleri "$PY" scripts/capture_screenshots.py "$OUT/ekran_goruntuleri"
else
    log "GUI ölçümleri atlandı: grafik oturumu (DISPLAY/WAYLAND_DISPLAY) bulunamadı."
fi

log "Bitti. Sonuçlar: $OUT"
log "Elle yapılacak kontroller için PARDUS_VALIDATION.md listesine bakın."
