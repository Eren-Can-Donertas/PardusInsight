"""Uyarı listesi, ayrıntı paneli ve kural durumu tablosu."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QHeaderView, QLabel, QListWidget, QListWidgetItem, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..analysis.explain import alert_to_html
from ..core.formatting import fmt_time
from ..core.models import SEVERITY_ORDER, Alert, RuleStatus
from .charts import STATUS

SEVERITY_ICON = {"critical": "⛔", "warning": "⚠", "info": "ℹ"}
EMPTY_HTML = ("<h3>Uyarı seçilmedi</h3><p>Kurallar her örnekten sonra son pencereler "
              "üzerinde yeniden değerlendirilir. Koşullar sağlandığında uyarı burada "
              "tetikleyici metrikler, zaman aralığı ve belirsizlik açıklamasıyla listelenir.</p>"
              "<p>Aşağıdaki <b>Kural durumu</b> tablosu, her kuralın neden "
              "tetiklenmediğini de gösterir.</p>")


class AlertsPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.summary = QLabel("Aktif uyarı yok.")
        self.summary.setWordWrap(True)
        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        self.list.setAccessibleName("Uyarı listesi")
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        self.detail.setHtml(EMPTY_HTML)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["Kural", "Durum", "Son değerlendirme"])
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.status_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.status_table.setMaximumHeight(130)
        self.status_table.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(splitter, 1)
        layout.addWidget(QLabel("<b>Kural durumu</b>"))
        layout.addWidget(self.status_table)

        self._alerts: Dict[str, Alert] = {}
        self._signature: tuple = ()
        self._user_choice: Optional[str] = None  # kullanıcının kendisinin seçtiği uyarı
        self._programmatic = False
        self.list.currentItemChanged.connect(self._on_current_changed)

    def selected_alert_id(self) -> Optional[str]:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _on_current_changed(self, current: Optional[QListWidgetItem], previous=None) -> None:
        if not self._programmatic and current is not None:
            self._user_choice = current.data(Qt.ItemDataRole.UserRole)
        self._show_current(current, previous)

    def set_alerts(self, alerts: Sequence[Alert]) -> None:
        signature = tuple((a.alert_id, a.last_seen, a.resolved_at) for a in alerts)
        if signature == self._signature:
            return
        self._signature = signature
        selected = self._user_choice
        self._alerts = {a.alert_id: a for a in alerts}
        ordered = sorted(alerts, key=lambda a: (not a.active,
                                                -SEVERITY_ORDER.get(a.severity, 0),
                                                -a.last_seen))
        self.list.blockSignals(True)
        self.list.clear()
        for a in ordered:
            state = "AKTİF" if a.active else f"çözüldü {fmt_time(a.resolved_at)}"
            item = QListWidgetItem(
                f"{SEVERITY_ICON.get(a.severity, '•')} {a.title}\n"
                f"   {a.severity_label} · {fmt_time(a.first_seen)}–{fmt_time(a.last_seen)}"
                f" · {state}")
            item.setData(Qt.ItemDataRole.UserRole, a.alert_id)
            item.setToolTip(a.summary)
            if a.active:
                color = QColor(STATUS.get(a.severity, STATUS["info"]))
                color.setAlpha(60)
                item.setBackground(color)
            self.list.addItem(item)
        self.list.blockSignals(False)
        active = [a for a in alerts if a.active]
        if active:
            self.summary.setText(f"<b>{len(active)} aktif uyarı</b> · toplam {len(alerts)} kayıt. "
                                 "Ayrıntı için listeden seçin.")
        else:
            self.summary.setText(f"Aktif uyarı yok · toplam {len(alerts)} kayıt.")
        target = selected if selected in self._alerts else (
            ordered[0].alert_id if ordered else None)
        self._select(target)

    def _select(self, alert_id: Optional[str]) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == alert_id:
                self._programmatic = True
                try:
                    self.list.setCurrentItem(item)
                finally:
                    self._programmatic = False
                self._show_current(item, None)
                return
        self.detail.setHtml(EMPTY_HTML)

    def _show_current(self, current: Optional[QListWidgetItem], _previous=None) -> None:
        if current is None:
            self.detail.setHtml(EMPTY_HTML)
            return
        alert = self._alerts.get(current.data(Qt.ItemDataRole.UserRole))
        if alert is not None:
            scroll = self.detail.verticalScrollBar().value()
            self.detail.setHtml(alert_to_html(alert))
            self.detail.verticalScrollBar().setValue(scroll)

    def set_statuses(self, statuses: Sequence[RuleStatus]) -> None:
        self.status_table.setRowCount(len(statuses))
        for row, st in enumerate(statuses):
            state = "Tetiklendi" if st.triggered else "Sakin"
            for col, text in enumerate((st.title, state, st.reason)):
                item = QTableWidgetItem(text)
                item.setToolTip(st.reason)
                self.status_table.setItem(row, col, item)
        self.status_table.resizeRowsToContents()
