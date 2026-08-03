"""Просмотрщик экспорта (журнала испытаний).

Слева — список испытаний (№, дата, ГОСТ/методика, образец, статус), справа —
детали выбранного: шапка + вкладки «События» и «Измерения». Данные берутся
из export.py (SQLite). Только чтение; запись ведёт ход испытания.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QComboBox,
    QAbstractItemView, QSplitter, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

from export import export

_STATUS_COLOR = {
    export.STATUS_RUNNING:   "#2980b9",
    export.STATUS_DONE:      "#27ae60",
    export.STATUS_INTERRUPT: "#e0a030",
    export.STATUS_ALARM:     "#c0392b",
}


class ExportViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Экспорт")
        self.setMinimumSize(900, 560)
        self._current_id = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addLayout(self._build_toolbar())

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_list())
        split.addWidget(self._build_details())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 4)
        root.addWidget(split, 1)

        self._apply_style()
        self.reload()

    # ── панель инструментов ─────────────────────────────────────────────────
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)
        title = QLabel("Экспорт")
        title.setObjectName("h1")
        bar.addWidget(title, 1)

        bar.addWidget(QLabel("Статус:"))
        self._cb_status = QComboBox()
        self._cb_status.addItem("Все", None)
        for s in (export.STATUS_RUNNING, export.STATUS_DONE,
                  export.STATUS_INTERRUPT, export.STATUS_ALARM):
            self._cb_status.addItem(s, s)
        self._cb_status.currentIndexChanged.connect(self.reload)
        bar.addWidget(self._cb_status)

        btn_reload = QPushButton("⟳ Обновить")
        btn_reload.clicked.connect(self.reload)
        bar.addWidget(btn_reload)
        return bar

    # ── список испытаний ────────────────────────────────────────────────────
    def _build_list(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(8, 8, 8, 8)

        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["№", "Начало", "ГОСТ / методика", "Образец", "Статус"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tbl.itemSelectionChanged.connect(self._on_select)
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._tbl)
        return f

    # ── детали выбранного испытания ─────────────────────────────────────────
    def _build_details(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._lbl_head = QLabel("Выберите испытание из списка")
        self._lbl_head.setObjectName("h2")
        self._lbl_head.setWordWrap(True)
        lay.addWidget(self._lbl_head)

        self._lbl_meta = QLabel("")
        self._lbl_meta.setWordWrap(True)
        self._lbl_meta.setObjectName("muted")
        lay.addWidget(self._lbl_meta)

        tabs = QTabWidget()
        self._tbl_events = self._make_table(["Время", "Шаг", "Сообщение"])
        self._tbl_meas   = self._make_table(["Время", "Шаг", "Параметр", "Значение", "Ед."])
        tabs.addTab(self._tbl_events, "События")
        tabs.addTab(self._tbl_meas, "Измерения")
        lay.addWidget(tabs, 1)
        return f

    def _make_table(self, headers: list[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    # ── загрузка данных ─────────────────────────────────────────────────────
    def reload(self):
        status = self._cb_status.currentData()
        rows = export.list_tests(status=status)
        self._tbl.setRowCount(0)
        for r in rows:
            i = self._tbl.rowCount()
            self._tbl.insertRow(i)
            sample = r.get("sample_name") or r.get("sample_id") or "—"
            gm = " / ".join(x for x in (r.get("gost"), r.get("method")) if x) or "—"
            cells = [str(r["id"]), r.get("start_ts") or "", gm, sample, r.get("status") or ""]
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, r["id"])
                if col == 4:
                    it.setForeground(QColor(_STATUS_COLOR.get(r.get("status"), "#cccccc")))
                self._tbl.setItem(i, col, it)
        # сохранить выбор, если возможно
        if self._current_id is not None:
            self._select_id(self._current_id)

    def _select_id(self, test_id: int):
        for i in range(self._tbl.rowCount()):
            if self._tbl.item(i, 0).data(Qt.ItemDataRole.UserRole) == test_id:
                self._tbl.selectRow(i)
                return

    def _on_select(self):
        items = self._tbl.selectedItems()
        if not items:
            return
        test_id = items[0].data(Qt.ItemDataRole.UserRole)
        self._current_id = test_id
        self._show_details(test_id)

    def _show_details(self, test_id: int):
        t = export.get_test(test_id)
        if not t:
            return
        self._lbl_head.setText(
            f"Испытание №{t['id']} — {t.get('gost') or ''} {t.get('method') or ''}".strip())
        meta = [
            ("Статус", t.get("status")),
            ("Начало", t.get("start_ts")),
            ("Окончание", t.get("end_ts") or "—"),
            ("Стенд", t.get("stand") or "—"),
            ("Образец", t.get("sample_name") or "—"),
            ("Шифр", t.get("sample_id") or "—"),
            ("Оператор", t.get("operator") or "—"),
        ]
        if t.get("interrupt_reason"):
            meta.append(("Причина прерывания", t["interrupt_reason"]))
        self._lbl_meta.setText("   ·   ".join(f"{k}: {v}" for k, v in meta))

        self._fill_table(self._tbl_events, export.get_events(test_id),
                         lambda e: [e.get("ts"), e.get("step"), e.get("message")])
        self._fill_table(self._tbl_meas, export.get_measurements(test_id),
                         lambda m: [m.get("ts"), m.get("step"), m.get("name"),
                                    m.get("value"), m.get("unit")])

    @staticmethod
    def _fill_table(tbl: QTableWidget, rows: list[dict], cols):
        tbl.setRowCount(0)
        for r in rows:
            i = tbl.rowCount()
            tbl.insertRow(i)
            for col, val in enumerate(cols(r)):
                tbl.setItem(i, col, QTableWidgetItem("" if val is None else str(val)))

    def set_theme(self, dark: bool):
        """Смена темы приложения — главное окно зовёт это у страниц стека."""
        self._apply_style(dark)

    def _apply_style(self, dark: bool = None):
        """Оформление по палитре приложения.

        Раньше цвета были вписаны прямо здесь и всегда тёмные — на светлой теме
        страница оставалась чёрной. Теперь берём их из палитры: те же роли, что
        и у остальных окон.
        """
        app = QApplication.instance()
        pal = app.palette() if app is not None else self.palette()
        R = QPalette.ColorRole
        if dark is None:
            dark = pal.color(R.Window).lightness() < 128
        bg     = pal.color(R.Window).name()          # общий фон страницы
        card   = pal.color(R.AlternateBase).name()   # карточка/шапка
        field  = pal.color(R.Base).name()            # таблицы и поля ввода
        text   = pal.color(R.WindowText).name()
        border = pal.color(R.Mid).name()
        btn    = pal.color(R.Button).name()
        muted  = pal.color(R.PlaceholderText).name()
        sel    = pal.color(R.Highlight).name()
        sel_tx = pal.color(R.HighlightedText).name()
        hover  = QColor(btn).lighter(115).name() if dark else QColor(btn).darker(108).name()
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {text}; font-size: 13px; }}
            QLabel#h1 {{ font-size: 16px; font-weight: bold; color: #1abc9c; }}
            QLabel#h2 {{ font-size: 15px; font-weight: bold; }}
            QLabel#muted {{ color: {muted}; font-size: 12px; }}
            QFrame#card {{ background: {card}; border: 1px solid {border};
                           border-radius: 8px; }}
            QTableWidget {{ background: {field}; border: 1px solid {border};
                            border-radius: 6px; gridline-color: {border}; }}
            QHeaderView::section {{ background: {card}; color: {text}; border: none;
                                    padding: 5px; font-weight: bold; }}
            QTableWidget::item:selected {{ background: {sel}; color: {sel_tx}; }}
            QPushButton {{ background: {btn}; border: 1px solid {border};
                           border-radius: 6px; padding: 5px 12px; }}
            QPushButton:hover {{ background: {hover}; }}
            QComboBox {{ background: {field}; border: 1px solid {border};
                         border-radius: 6px; padding: 3px 8px; }}
            QTabWidget::pane {{ border: 1px solid {border}; border-radius: 6px; }}
            QTabBar::tab {{ background: {card}; color: {text}; padding: 6px 14px;
                            border-top-left-radius: 6px; border-top-right-radius: 6px; }}
            QTabBar::tab:selected {{ background: #1abc9c; color: #10141a;
                                     font-weight: bold; }}
        """)


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = ExportViewer()
    w.show()
    sys.exit(app.exec())
