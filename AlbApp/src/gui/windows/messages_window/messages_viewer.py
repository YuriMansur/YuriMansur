"""Страница «Сообщения» — просмотр системного лога приложения (applog).

Показывает связь с ПЛК, аварии, действия оператора и системные события из
logs.db. Фильтр по уровню/категории, автообновление, ретенция (очистка старых).
Стиль наследует палитру приложения, поэтому следует светлой/тёмной теме.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit, QTimeEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from collections import deque

from PyQt6.QtCore import Qt, QTimer, QDate, QTime
from PyQt6.QtGui import QColor

from logger import applog
from event_bus import bus

_BUFFER_SIZE = 2000   # кольцевой буфер «временных событий» сессии (RAM)

_LEVEL_COLOR = {
    applog.LEVEL_INFO:  "#27ae60",
    applog.LEVEL_WARN:  "#e0a030",
    applog.LEVEL_ALARM: "#c0392b",
}
_TITLE_STYLE = "font-size: 15px; font-weight: bold; color: #e67e22;"


class MessagesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # авто-ретенция: при запуске удаляем записи старше 30 дней (раньше это
        # делала кнопка «Очистить старые» вручную — теперь автоматически)
        applog.purge(30)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addLayout(self._build_toolbar())

        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Время", "Уровень", "Источник", "Сообщение"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # мягкая светло-серая сетка для разделения колонок + белый контур виджета
        self._tbl.setShowGrid(True)
        self._tbl.setStyleSheet(
            "QTableWidget { gridline-color: #9aa5b1;"
            " border: 2px solid #ffffff; border-radius: 4px; }")
        hh = self._tbl.horizontalHeader()
        for col in (0, 1, 2):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._tbl, 1)

        # «Временные события» — кольцевой буфер в памяти (живые события сессии).
        # «Архив» — БД logs.db. Переключение тоглом «Источник».
        self._buffer = deque(maxlen=_BUFFER_SIZE)
        bus.log_event.connect(self._on_log_event)

        # архив сам не обновляется — освежаем его по таймеру (в режиме «События»
        # это не нужно: буфер живёт по сигналу)
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._auto_archive_reload)
        self._timer.start()

        self._apply_date_range(reset_selection=True)
        self.reload()

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)
        title = QLabel("Сообщения")
        title.setStyleSheet(_TITLE_STYLE)
        bar.addWidget(title, 1)

        bar.addWidget(QLabel("Режим:"))
        self._cb_source = QComboBox()
        self._cb_source.addItem("События", "buffer")
        self._cb_source.addItem("Архив",   "archive")
        self._cb_source.setToolTip("События — живой буфер в памяти; Архив — записи из БД")
        self._cb_source.currentIndexChanged.connect(self.reload)
        bar.addWidget(self._cb_source)

        bar.addWidget(QLabel("Уровень:"))
        self._cb_level = QComboBox()
        self._cb_level.addItem("Все", None)
        for lv in (applog.LEVEL_INFO, applog.LEVEL_WARN, applog.LEVEL_ALARM):
            self._cb_level.addItem(lv, lv)
        self._cb_level.currentIndexChanged.connect(self.reload)
        bar.addWidget(self._cb_level)

        bar.addWidget(QLabel("Источник:"))
        self._cb_cat = QComboBox()
        self._cb_cat.addItem("Все", None)
        for cat in (applog.CAT_CONN, applog.CAT_PLC, applog.CAT_ACTION, applog.CAT_SYS):
            self._cb_cat.addItem(cat, cat)
        self._cb_cat.currentIndexChanged.connect(self.reload)
        bar.addWidget(self._cb_cat)

        # пределы дат задаются по фактическому диапазону данных в _apply_date_range
        bar.addWidget(QLabel("С:"))
        self._date_from = QDateEdit()
        self._date_from.setDisplayFormat("dd.MM.yyyy")
        self._date_from.setCalendarPopup(True)
        self._date_from.dateChanged.connect(self.reload)
        bar.addWidget(self._date_from)
        self._time_from = QTimeEdit(QTime(0, 0, 0))
        self._time_from.setDisplayFormat("HH:mm:ss")
        self._time_from.timeChanged.connect(self.reload)
        bar.addWidget(self._time_from)

        bar.addWidget(QLabel("По:"))
        self._date_to = QDateEdit()
        self._date_to.setDisplayFormat("dd.MM.yyyy")
        self._date_to.setCalendarPopup(True)
        self._date_to.dateChanged.connect(self.reload)
        bar.addWidget(self._date_to)
        self._time_to = QTimeEdit(QTime(23, 59, 59))
        self._time_to.setDisplayFormat("HH:mm:ss")
        self._time_to.timeChanged.connect(self.reload)
        bar.addWidget(self._time_to)

        return bar

    # ── данные ───────────────────────────────────────────────────────────────
    def showEvent(self, event):
        # при открытии вкладки обновляем пределы дат под актуальные данные и
        # подтягиваем архив из БД (синхронизируем real-time строки)
        super().showEvent(event)
        self._apply_date_range()
        self.reload()

    def _apply_date_range(self, reset_selection: bool = False):
        """Ограничить пикеры дат фактическим диапазоном данных в логе.

        reset_selection=True — выставить выбор на весь диапазон (при инициализации).
        Иначе меняем только пределы; текущий выбор сам зажмётся в новые границы.
        """
        # границы — строго по фактическому диапазону данных (старше 30 дней
        # вычищается ретенцией, так что показываем сколько данных есть)
        lo, hi = applog.ts_range()
        if lo and hi:
            d_lo = QDate.fromString(lo[:10], "yyyy-MM-dd")
            d_hi = QDate.fromString(hi[:10], "yyyy-MM-dd")
        else:
            d_lo = d_hi = QDate.currentDate()
        for de in (self._date_from, self._date_to):
            de.blockSignals(True)
            de.setDateRange(d_lo, d_hi)
            de.blockSignals(False)
        if reset_selection:
            for de, d in ((self._date_from, d_lo), (self._date_to, d_hi)):
                de.blockSignals(True)
                de.setDate(d)
                de.blockSignals(False)

    def _auto_archive_reload(self):
        # автообновление только для архива и только когда вкладка видима;
        # в режиме «События» буфер обновляется сам по сигналу
        if self.isVisible() and self._cb_source.currentData() == "archive":
            self.reload()

    def _insert_row(self, index: int, rec: dict):
        self._tbl.insertRow(index)
        cells = [rec.get("ts") or "", rec.get("level") or "",
                 rec.get("category") or "", rec.get("message") or ""]
        for col, text in enumerate(cells):
            it = QTableWidgetItem(text)
            if col == 1:
                it.setForeground(QColor(_LEVEL_COLOR.get(rec.get("level"), "#888888")))
            self._tbl.setItem(index, col, it)

    def _date_bounds(self) -> tuple[str, str]:
        """Границы периода (дата+время) как строки ts (ISO сравнивается лексикографически)."""
        since = (self._date_from.date().toString("yyyy-MM-dd") + " " +
                 self._time_from.time().toString("HH:mm:ss"))
        until = (self._date_to.date().toString("yyyy-MM-dd") + " " +
                 self._time_to.time().toString("HH:mm:ss"))
        return since, until

    def _matches_filter(self, rec: dict) -> bool:
        lv  = self._cb_level.currentData()
        cat = self._cb_cat.currentData()
        if lv and rec.get("level") != lv:
            return False
        if cat and rec.get("category") != cat:
            return False
        since, until = self._date_bounds()
        ts = rec.get("ts") or ""
        if ts < since or ts > until:
            return False
        return True

    def _on_log_event(self, rec: dict):
        # буфер пополняется всегда; в таблицу пишем сразу только в режиме «События»
        self._buffer.append(rec)
        if self._cb_source.currentData() == "buffer" and self._matches_filter(rec):
            self._insert_row(0, rec)
            if self._tbl.rowCount() > _BUFFER_SIZE:        # держим таблицу в пределах буфера
                self._tbl.removeRow(self._tbl.rowCount() - 1)

    def reload(self):
        if self._cb_source.currentData() == "archive":
            since, until = self._date_bounds()
            rows = applog.list_logs(level=self._cb_level.currentData(),
                                    category=self._cb_cat.currentData(),
                                    since=since, until=until)
        else:
            # буфер хранит от старых к новым; выводим новыми сверху
            rows = [r for r in reversed(self._buffer) if self._matches_filter(r)]
        sb = self._tbl.verticalScrollBar()
        pos = sb.value()
        self._tbl.setRowCount(0)
        for r in rows:
            self._insert_row(self._tbl.rowCount(), r)
        sb.setValue(min(pos, sb.maximum()))

    def set_theme(self, dark: bool):
        # стиль наследуется из палитры приложения; явных действий не требуется
        self.reload()
