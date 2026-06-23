"""Страница «Сообщения» — просмотр системного лога приложения (applog).

Показывает связь с ПЛК, аварии, действия оператора и системные события из
logs.db. Фильтр по уровню/категории, автообновление, ретенция (очистка старых).
Стиль наследует палитру приложения, поэтому следует светлой/тёмной теме.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from logger import applog

_LEVEL_COLOR = {
    applog.LEVEL_INFO:  "#27ae60",
    applog.LEVEL_WARN:  "#e0a030",
    applog.LEVEL_ALARM: "#c0392b",
}
_TITLE_STYLE = "font-size: 15px; font-weight: bold; color: #e67e22;"


class MessagesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addLayout(self._build_toolbar())

        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["Время", "Уровень", "Категория", "Источник", "Сообщение"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self._tbl.horizontalHeader()
        for col in (0, 1, 2, 3):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._tbl, 1)

        # автообновление, пока страница видима
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._auto_reload)
        self._timer.start()

        self.reload()

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)
        title = QLabel("Сообщения")
        title.setStyleSheet(_TITLE_STYLE)
        bar.addWidget(title, 1)

        bar.addWidget(QLabel("Уровень:"))
        self._cb_level = QComboBox()
        self._cb_level.addItem("Все", None)
        for lv in (applog.LEVEL_INFO, applog.LEVEL_WARN, applog.LEVEL_ALARM):
            self._cb_level.addItem(lv, lv)
        self._cb_level.currentIndexChanged.connect(self.reload)
        bar.addWidget(self._cb_level)

        bar.addWidget(QLabel("Категория:"))
        self._cb_cat = QComboBox()
        self._cb_cat.addItem("Все", None)
        for cat in (applog.CAT_CONN, applog.CAT_PLC, applog.CAT_ACTION, applog.CAT_SYS):
            self._cb_cat.addItem(cat, cat)
        self._cb_cat.currentIndexChanged.connect(self.reload)
        bar.addWidget(self._cb_cat)

        btn_reload = QPushButton("⟳ Обновить")
        btn_reload.clicked.connect(self.reload)
        bar.addWidget(btn_reload)

        btn_purge = QPushButton("🧹 Очистить старые")
        btn_purge.setToolTip("Удалить записи старше 30 дней")
        btn_purge.clicked.connect(self._purge)
        bar.addWidget(btn_purge)
        return bar

    # ── данные ───────────────────────────────────────────────────────────────
    def _auto_reload(self):
        if self.isVisible():
            self.reload()

    def reload(self):
        rows = applog.list_logs(level=self._cb_level.currentData(),
                                category=self._cb_cat.currentData())
        # сохранить вертикальную прокрутку, чтобы не дёргалось при автообновлении
        sb = self._tbl.verticalScrollBar()
        pos = sb.value()
        self._tbl.setRowCount(0)
        for r in rows:
            i = self._tbl.rowCount()
            self._tbl.insertRow(i)
            cells = [r.get("ts") or "", r.get("level") or "", r.get("category") or "",
                     r.get("source") or "", r.get("message") or ""]
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if col == 1:
                    it.setForeground(QColor(_LEVEL_COLOR.get(r.get("level"), "#888888")))
                self._tbl.setItem(i, col, it)
        sb.setValue(min(pos, sb.maximum()))

    def _purge(self):
        applog.purge(30)
        self.reload()

    def set_theme(self, dark: bool):
        # стиль наследуется из палитры приложения; явных действий не требуется
        self.reload()
