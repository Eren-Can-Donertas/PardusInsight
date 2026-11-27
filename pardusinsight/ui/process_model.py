"""Süreç tablosu modeli (salt-okunur; süreçler üzerinde hiçbir eylem sunulmaz)."""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from ..core.formatting import NA, fmt_bytes, fmt_rate, tr_num
from ..core.models import ProcessInfo

Index = Union[QModelIndex, QPersistentModelIndex]

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
PID_ROLE = Qt.ItemDataRole.UserRole + 2

Column = Tuple[str, Callable[[ProcessInfo], Any], Callable[[Any], str], bool, str]


def _num(digits: int) -> Callable[[Any], str]:
    return lambda v: NA if v is None else tr_num(v, digits)


#: psutil/çekirdek süreç durumlarının Türkçe karşılıkları
STATUS_TR = {
    "running": "çalışıyor (R)", "sleeping": "uyuyor (S)", "disk-sleep": "G/Ç bekliyor (D)",
    "stopped": "durduruldu (T)", "tracing-stop": "izleniyor (t)", "zombie": "zombi (Z)",
    "dead": "sonlanmış (X)", "idle": "boşta (I)", "parked": "park (P)", "waking": "uyanıyor",
    "wake-kill": "uyandır-sonlandır",
}


def _status(value: Any) -> str:
    return NA if not value else STATUS_TR.get(str(value), str(value))


COLUMNS: List[Column] = [
    # başlık, değer, biçimlendirici, sayısal mı, ipucu
    ("PID", lambda p: p.pid, str, True, "Süreç kimliği"),
    ("Ad", lambda p: p.name, str, False, "Süreç adı"),
    ("Kullanıcı", lambda p: p.username, lambda v: v or NA, False, "Sürecin sahibi"),
    ("Durum", lambda p: p.status, _status, False,
     "Çekirdek süreç durumu; 'G/Ç bekliyor (D)' kesintisiz disk beklemesidir"),
    ("CPU %", lambda p: p.cpu_percent, _num(1), True,
     "Toplam CPU kapasitesine göre pay (tüm çekirdekler = %100)"),
    ("RSS", lambda p: p.rss_bytes, fmt_bytes, True,
     "Fiziksel bellekteki yerleşik boyut (paylaşılan sayfalar dahil)"),
    ("Bellek %", lambda p: p.memory_percent, _num(1), True, "RSS / toplam RAM"),
    ("İş parç.", lambda p: p.num_threads, lambda v: NA if v is None else str(v), True,
     "İş parçacığı (thread) sayısı"),
    ("Okuma/sn", lambda p: p.read_bytes_per_s, fmt_rate, True,
     "Depolama katmanından okuma hızı; başka kullanıcıların süreçlerinde root olmadan okunamaz"),
    ("Yazma/sn", lambda p: p.write_bytes_per_s, fmt_rate, True,
     "Depolama katmanına yazma hızı; başka kullanıcıların süreçlerinde root olmadan okunamaz"),
]


class ProcessTableModel(QAbstractTableModel):
    """Sıralama ve filtreleme Python tarafında, satır listesi üzerinde yapılır.

    QSortFilterProxyModel her karşılaştırmada data() çağırdığı için ~500 süreçte tur başına
    binlerce Python çağrısına yol açıyordu; burada sıralama tek bir sorted() çağrısıdır ve
    data() yalnızca ekranda görünen hücreler için çalışır.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all: List[ProcessInfo] = []
        self._rows: List[ProcessInfo] = []
        self._sort_column = 4
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._needle = ""

    def set_processes(self, processes: Sequence[ProcessInfo]) -> None:
        self._all = list(processes)
        self._rebuild()

    def set_filter(self, text: str) -> None:
        self._needle = text.strip().lower()
        self._rebuild()

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self._sort_column = column
        self._sort_order = order
        self._rebuild()

    def _accept(self, proc: ProcessInfo) -> bool:
        needle = self._needle
        return (not needle or needle in proc.name.lower()
                or needle in (proc.username or "").lower() or needle == str(proc.pid))

    def _rebuild(self) -> None:
        _title, getter, _fmt, numeric, _tip = COLUMNS[self._sort_column]
        if numeric:
            def key(p: ProcessInfo) -> Any:
                value = getter(p)
                return float("-inf") if value is None else float(value)
        else:
            def key(p: ProcessInfo) -> Any:
                return (getter(p) or "").lower()
        rows = [p for p in self._all if self._accept(p)]
        rows.sort(key=key, reverse=self._sort_order == Qt.SortOrder.DescendingOrder)
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def process_at(self, row: int) -> Optional[ProcessInfo]:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of_pid(self, pid: int) -> Optional[int]:
        for row, proc in enumerate(self._rows):
            if proc.pid == pid:
                return row
        return None

    def rowCount(self, parent: Index = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: Index = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        proc = self._rows[index.row()]
        _title, getter, fmt, numeric, _tip = COLUMNS[index.column()]
        value = getter(proc)
        if role == Qt.ItemDataRole.DisplayRole:
            return fmt(value)
        if role == SORT_ROLE:
            if numeric:
                return -1.0 if value is None else float(value)
            return (value or "").lower()
        if role == PID_ROLE:
            return proc.pid
        if role == Qt.ItemDataRole.TextAlignmentRole and numeric:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and value is None:
            return "Erişilemedi: bu alan standart kullanıcı yetkisiyle okunamıyor."
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,  # noqa: N802
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        if role == Qt.ItemDataRole.ToolTipRole:
            return COLUMNS[section][4]
        return None
