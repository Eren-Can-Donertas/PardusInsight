"""QPainter ile çizilen hafif zaman serisi grafiği (ek bağımlılık gerektirmez).

Tasarım kuralları: tek y ekseni, en fazla iki seri, her zaman lejant, ince
(2 px) çizgiler, silik ızgara. Uyarı zaman aralıkları durum rengiyle ve
etiketle gölgelenir (renk tek başına anlam taşımaz). Fare ile üzerine
gelindiğinde dikey imleç ve değerleri gösteren ipucu çıkar.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..core.formatting import fmt_time, tr_num
from ..core.models import SystemSample

Getter = Callable[[SystemSample], Optional[float]]

# Doğrulanmış kategorik palet (açık / koyu tema için ayrı seçilmiş adımlar)
SERIES_COLORS = {
    "light": ("#2a78d6", "#eb6834"),
    "dark": ("#3987e5", "#d95926"),
}
GRID = {"light": "#e1e0d9", "dark": "#2c2c2a"}
AXIS = {"light": "#c3c2b7", "dark": "#383835"}
STATUS = {"warning": "#fab219", "critical": "#d03b3b", "info": "#8a8a85"}


@dataclass(frozen=True)
class SeriesSpec:
    label: str
    getter: Getter


@dataclass(frozen=True)
class Span:
    start: float
    end: float
    severity: str
    label: str


def nice_ceiling(value: float) -> float:
    """Eksen üst sınırı için 1-2-5 dizisinden yuvarlak değer."""
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10 ** exponent
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * base:
            return step * base
    return 10 * base  # pragma: no cover


class TimeSeriesChart(QWidget):
    def __init__(self, title: str, unit: str, series: Sequence[SeriesSpec],
                 fixed_max: Optional[float] = None, value_digits: int = 1,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.series = list(series)[:2]
        self.fixed_max = fixed_max
        self.value_digits = value_digits
        self.threshold: Optional[Tuple[float, str]] = None
        self._samples: List[SystemSample] = []
        self._times: List[float] = []
        self._span_s = 300.0
        self._now = 0.0
        self._spans: List[Span] = []
        self._hover_x: Optional[float] = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(title)

    # -- veri ---------------------------------------------------------------
    def set_threshold(self, value: Optional[float], label: str = "eşik") -> None:
        self.threshold = None if value is None else (value, label)
        self.update()

    def set_data(self, samples: Sequence[SystemSample], span_s: float,
                 now: Optional[float] = None) -> None:
        self._span_s = max(span_s, 10.0)
        self._now = now if now is not None else (samples[-1].timestamp if samples else 0.0)
        start = self._now - self._span_s
        self._samples = [s for s in samples if s.timestamp >= start]
        self._times = [s.timestamp for s in self._samples]
        self.update()

    def set_spans(self, spans: Sequence[Span]) -> None:
        self._spans = list(spans)
        self.update()

    def point_count(self) -> int:
        return len(self._samples)

    # -- yardımcılar ----------------------------------------------------------
    def _mode(self) -> str:
        return "dark" if self.palette().window().color().lightness() < 128 else "light"

    def _y_max(self) -> float:
        if self.fixed_max is not None:
            return self.fixed_max
        peak = 0.0
        for spec in self.series:
            for s in self._samples:
                v = spec.getter(s)
                if v is not None and v > peak:
                    peak = v
        if self.threshold is not None:
            peak = max(peak, self.threshold[0])
        # Dört eşit ve yuvarlak ızgara aralığı (ör. 0-1-2-3-4, 0-250-...-1000)
        return nice_ceiling((peak * 1.1 if peak > 0 else 1.0) / 4.0) * 4.0

    def _plot_rect(self) -> QRectF:
        return QRectF(52.0, 30.0, max(self.width() - 64.0, 10.0),
                      max(self.height() - 54.0, 10.0))

    def _fmt(self, value: Optional[float]) -> str:
        if value is None:
            return "—"
        digits = self.value_digits if abs(value) < 100 else 0
        if self.unit == "%":
            return f"%{tr_num(value, digits)}"
        return f"{tr_num(value, digits)} {self.unit}".strip()

    def _x_of(self, t: float, rect: QRectF) -> float:
        return rect.left() + (t - (self._now - self._span_s)) / self._span_s * rect.width()

    # -- çizim ----------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API adı)
        mode = self._mode()
        pal = self.palette()
        text = pal.windowText().color()
        muted = QColor(text)
        muted.setAlpha(150)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), pal.base())
        rect = self._plot_rect()
        y_max = self._y_max()

        # Başlık ve lejant (metin rengi; seri rengi yalnızca işaretçide)
        title_font = QFont(self.font())
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(text)
        p.drawText(QRectF(8, 4, self.width() * 0.5, 22),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(self.font())
        latest = self._samples[-1] if self._samples else None
        x = self.width() - 8.0
        for idx in range(len(self.series) - 1, -1, -1):
            spec = self.series[idx]
            label = f"{spec.label}: {self._fmt(spec.getter(latest) if latest else None)}"
            w = p.fontMetrics().horizontalAdvance(label)
            x -= w
            p.setPen(text)
            p.drawText(QRectF(x, 4, w + 2, 22), Qt.AlignmentFlag.AlignVCenter, label)
            x -= 16
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(SERIES_COLORS[mode][idx]))
            p.drawRoundedRect(QRectF(x, 11, 10, 10), 2, 2)
            x -= 14

        # Izgara ve eksen etiketleri
        grid_pen = QPen(QColor(GRID[mode]), 1)
        for i in range(5):
            frac = i / 4
            y = rect.bottom() - frac * rect.height()
            p.setPen(grid_pen if i else QPen(QColor(AXIS[mode]), 1))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(muted)
            tick = y_max * frac
            digits = 0 if float(tick).is_integer() else (1 if (tick * 10).is_integer() else 2)
            p.drawText(QRectF(0, y - 9, rect.left() - 6, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       tr_num(tick, digits))
        minutes = self._span_s / 60.0
        for frac, label in ((0.0, f"-{tr_num(minutes, 0 if minutes >= 1 else 1)} dk"),
                            (0.5, f"-{tr_num(minutes / 2, 0 if minutes >= 2 else 1)} dk"),
                            (1.0, "şimdi")):
            xx = rect.left() + frac * rect.width()
            align = (Qt.AlignmentFlag.AlignLeft if frac == 0 else
                     Qt.AlignmentFlag.AlignRight if frac == 1 else Qt.AlignmentFlag.AlignHCenter)
            box = QRectF(xx - (0 if frac == 0 else 80 if frac == 1 else 40), rect.bottom() + 4,
                         80, 18)
            p.drawText(box, align | Qt.AlignmentFlag.AlignTop, label)

        p.save()
        p.setClipRect(rect.adjusted(-1, -1, 1, 1))
        # Uyarı aralıkları: durum rengi + etiket
        for span in self._spans:
            x0 = max(self._x_of(span.start, rect), rect.left())
            x1 = min(self._x_of(span.end, rect), rect.right())
            if x1 <= rect.left() or x0 >= rect.right() or x1 <= x0:
                continue
            color = QColor(STATUS.get(span.severity, STATUS["info"]))
            color.setAlpha(45)
            p.fillRect(QRectF(x0, rect.top(), x1 - x0, rect.height()), color)
            if x1 - x0 > 40:
                p.setPen(text)
                p.drawText(QRectF(x0 + 3, rect.top() + 2, x1 - x0 - 6, 16),
                           Qt.AlignmentFlag.AlignLeft, span.label)

        # Eşik çizgisi
        if self.threshold is not None and 0 <= self.threshold[0] <= y_max:
            y = rect.bottom() - self.threshold[0] / y_max * rect.height()
            pen = QPen(muted, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.drawText(QRectF(rect.left() + 4, y - 16, 200, 14), Qt.AlignmentFlag.AlignLeft,
                       f"{self.threshold[1]} {self._fmt(self.threshold[0])}")

        # Seriler
        if not self._samples:
            p.setPen(muted)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Veri bekleniyor…")
        for idx, spec in enumerate(self.series):
            path = self._build_path(spec.getter, rect, y_max)
            pen = QPen(QColor(SERIES_COLORS[mode][idx]), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # Fare imleci
        if self._hover_x is not None and self._samples:
            p.setPen(QPen(muted, 1))
            p.drawLine(QPointF(self._hover_x, rect.top()), QPointF(self._hover_x, rect.bottom()))
        p.restore()
        p.end()

    def _build_path(self, getter: Getter, rect: QRectF, y_max: float) -> QPainterPath:
        """Veri boşluklarında çizgiyi keser; piksel başına min/maks tutarak seyreltir."""
        path = QPainterPath()
        pen_down = False
        last_bucket = None
        bucket: List[Tuple[float, float]] = []

        def flush() -> None:
            nonlocal pen_down
            if not bucket:
                return
            pts = bucket if len(bucket) <= 2 else [
                bucket[0], min(bucket, key=lambda q: q[1]), max(bucket, key=lambda q: q[1]),
                bucket[-1]]
            for px, py in pts:
                if pen_down:
                    path.lineTo(px, py)
                else:
                    path.moveTo(px, py)
                    pen_down = True
            bucket.clear()

        for s in self._samples:
            v = getter(s)
            if v is None:
                flush()
                pen_down = False
                last_bucket = None
                continue
            px = self._x_of(s.timestamp, rect)
            py = rect.bottom() - min(max(v, 0.0), y_max) / y_max * rect.height()
            b = int(px)
            if b != last_bucket:
                flush()
                last_bucket = b
            bucket.append((px, py))
        flush()
        return path

    # -- etkileşim -------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        rect = self._plot_rect()
        pos = event.position() if hasattr(event, "position") else event.pos()
        if not self._samples or not rect.contains(pos):
            self._hover_x = None
            QToolTip.hideText()
            self.update()
            return
        t = (self._now - self._span_s) + (pos.x() - rect.left()) / rect.width() * self._span_s
        i = bisect.bisect_left(self._times, t)
        candidates = [j for j in (i - 1, i) if 0 <= j < len(self._samples)]
        j = min(candidates, key=lambda k: abs(self._times[k] - t))
        sample = self._samples[j]
        self._hover_x = self._x_of(sample.timestamp, rect)
        lines = [fmt_time(sample.timestamp)]
        lines += [f"{spec.label}: {self._fmt(spec.getter(sample))}" for spec in self.series]
        QToolTip.showText(event.globalPosition().toPoint() if hasattr(event, "globalPosition")
                          else event.globalPos(), "\n".join(lines), self)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_x = None
        self.update()
        super().leaveEvent(event)
