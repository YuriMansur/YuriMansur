from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QDateTimeEdit, QComboBox, QLineEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt, QDateTime, pyqtSignal

from gui.windows.settings_window.F_parameters import GOST_OPTIONS

_ISO_10328_METHODS = ["6.4.4","16.3","17.4.5"]

METHOD_OPTIONS = {
    "Р53868-2021":       _ISO_10328_METHODS,
    "Р ИСО 10328-2021":  _ISO_10328_METHODS,
    "Р ИСО 15032-2001":  [],
}

_TITLE_STYLE = "font-size: 15px; font-weight: bold; color: #1abc9c;"

def _group_box(title: str, parent_layout: QVBoxLayout) -> QVBoxLayout:
    lbl = QLabel(title)
    lbl.setStyleSheet(_TITLE_STYLE)
    parent_layout.addWidget(lbl)
    inner = QVBoxLayout()
    inner.setContentsMargins(8, 0, 0, 4)
    inner.setSpacing(3)
    parent_layout.addLayout(inner)
    return inner


class Section2Widget(QWidget):
    params_changed = pyqtSignal(str, str)  # gost, method

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        from PyQt6.QtWidgets import QPushButton, QDialog
        btn_docs = QPushButton("📄 Документация (ГОСТ)")
        btn_docs.setMinimumHeight(36)
        btn_docs.setStyleSheet("font-size: 14px; padding: 6px 16px; border: 2px solid #1abc9c; border-radius: 4px;")
        from pathlib import Path
        _DOCS_DIR = Path(__file__).parent.parent.parent.parent.parent / "docs"
        btn_docs._pdf_windows = []

        def _open_pdf():
            from PyQt6.QtWidgets import QVBoxLayout
            from pdf_reader import PdfReaderWidget
            # убираем уже закрытые окна
            btn_docs._pdf_windows = [w for w in btn_docs._pdf_windows if w.isVisible()]
            max_windows = len(list(_DOCS_DIR.glob("*.pdf"))) if _DOCS_DIR.exists() else 1
            if len(btn_docs._pdf_windows) >= max_windows:
                btn_docs._pdf_windows[-1].raise_()
                btn_docs._pdf_windows[-1].activateWindow()
                return
            dlg = QDialog(btn_docs.window())
            dlg.setWindowTitle(f"Документация [{len(btn_docs._pdf_windows) + 1}]")
            dlg.setModal(False)
            dlg.resize(1100, 800)
            dlg_lay = QVBoxLayout(dlg)
            dlg_lay.setContentsMargins(0, 0, 0, 0)
            dlg_lay.addWidget(PdfReaderWidget())
            btn_docs._pdf_windows.append(dlg)
            dlg.show()
        btn_docs.clicked.connect(_open_pdf)
        layout.addWidget(btn_docs)

        layout.addSpacing(20)

        # ── Параметры оборудования стенда ────────────────────────────────────
        lbl_stand_title = QLabel("Параметры оборудования стенда")
        lbl_stand_title.setStyleSheet(_TITLE_STYLE)
        layout.addWidget(lbl_stand_title)

        grp_stand = QVBoxLayout()
        grp_stand.setContentsMargins(16, 4, 8, 12)
        grp_stand.setSpacing(5)
        layout.addLayout(grp_stand)

        try:
            import json as _json
            with open("params.json", "r", encoding="utf-8") as _f:
                _si = _json.load(_f).get("stand_info", {})
        except (FileNotFoundError, ValueError):
            _si = {}

        for label, key in [
            ("Марка и модель стенда:",  "stand_model"),
            ("Серийный номер стенда:",  "stand_serial"),
            ("Дата аттестации стенда:", "stand_date"),
            ("Марка и модель СИ 1:",    "si1_model"),
            ("Марка и модель СИ 2:",    "si2_model"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(10)
            lk = QLabel(label)
            lv = QLabel(_si.get(key, ""))
            row.addWidget(lk)
            row.addWidget(lv, 1)
            grp_stand.addLayout(row)
            grp_stand.addSpacing(4)

        # ── Параметры испытания ───────────────────────────────────────────────
        params_container = QWidget()
        params_container.setMinimumHeight(280)
        params_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        params_inner = QVBoxLayout(params_container)
        params_inner.setContentsMargins(0, 0, 0, 0)
        params_inner.setSpacing(0)
        layout.addWidget(params_container)

        grp2 = _group_box("Параметры испытания", params_inner)
        form2 = QFormLayout()
        form2.setSpacing(4)
        form2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cb_std = QComboBox()
        self.cb_std.addItems(GOST_OPTIONS.keys())
        form2.addRow("Стандарт проведения испытаний:", self.cb_std)

        self.cb_load = QComboBox()
        form2.addRow("Уровень нагружения:", self.cb_load)

        self.cb_cond = QComboBox()
        self._lbl_cond = QLabel("Условие нагружения:")
        for w in (self.cb_cond, self._lbl_cond):
            sp = w.sizePolicy(); sp.setRetainSizeWhenHidden(True); w.setSizePolicy(sp)
        form2.addRow(self._lbl_cond, self.cb_cond)

        _F_KEYS = ["Fset", "Fsp", "Fstab", "F_su_lower_level", "F_su_upper_level"]
        self._f_edits  = {}
        self._f_labels = {}
        for key in _F_KEYS:
            le  = QLineEdit(); le.setReadOnly(True)
            lbl = QLabel(f"{key}:")
            sp = le.sizePolicy(); sp.setRetainSizeWhenHidden(True); le.setSizePolicy(sp)
            sp = lbl.sizePolicy(); sp.setRetainSizeWhenHidden(True); lbl.setSizePolicy(sp)
            self._f_edits[key]  = le
            self._f_labels[key] = lbl
            form2.addRow(lbl, le)

        spacer_lbl = QLabel()
        spacer_lbl.setFixedHeight(8)
        form2.addRow(spacer_lbl)

        self.cb_method = QComboBox()
        self._lbl_method = QLabel("Методика:")
        form2.addRow(self._lbl_method, self.cb_method)

        self._form2 = form2
        grp2.addLayout(form2)

        layout.addSpacing(20)

        # ── Информация об образце ─────────────────────────────────────────────
        grp1 = _group_box("Информация об исследуемом образце", layout)
        form1 = QFormLayout()
        form1.setSpacing(4)
        form1.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        dt1 = QDateTimeEdit(QDateTime.currentDateTime())
        dt1.setDisplayFormat("dd.MM.yyyy"); dt1.setCalendarPopup(True)
        form1.addRow("Дата получения образца на:", dt1)

        dt2 = QDateTimeEdit(QDateTime.currentDateTime())
        dt2.setDisplayFormat("dd.MM.yyyy"); dt2.setCalendarPopup(True)
        form1.addRow("Дата проведения:", dt2)

        cb_used = QComboBox(); cb_used.addItems(["Нет", "Да"])
        form1.addRow("Образец используется:", cb_used)

        cb_replace = QComboBox(); cb_replace.addItems(["Нет", "Да"])
        form1.addRow("Образец используется взамен\nразрушенного:", cb_replace)

        le_clamp = QLineEdit(); le_clamp.setPlaceholderText("Введите значение")
        form1.addRow("Применяемые концевые крепления:", le_clamp)

        grp1.addLayout(form1)

        layout.addStretch()
        root.addWidget(container)
        root.addStretch()

        # ── Сигналы ───────────────────────────────────────────────────────────
        self.cb_std.currentTextChanged.connect(self._fill_load)
        self.cb_load.currentTextChanged.connect(lambda _: self._refresh_f())
        self.cb_cond.currentTextChanged.connect(lambda _: self._refresh_f())
        self.cb_std.currentTextChanged.connect(self._emit_params)
        self.cb_method.currentTextChanged.connect(self._emit_params)
        self._fill_load(self.cb_std.currentText())

    def _fill_load(self, gost: str):
        opts = GOST_OPTIONS.get(gost, {})

        self.cb_load.blockSignals(True)
        self.cb_load.clear()
        self.cb_load.addItems(opts.get("items", []))
        self.cb_load.blockSignals(False)

        has_i_ii = bool(opts.get("i_ii"))
        self.cb_cond.blockSignals(True)
        self.cb_cond.clear()
        if has_i_ii:
            self.cb_cond.addItems(["I", "II"])
        _hide = "color: transparent; background: transparent; border-color: transparent;"
        self.cb_cond.setStyleSheet("" if has_i_ii else _hide)
        self.cb_cond.setEnabled(has_i_ii)
        self._lbl_cond.setStyleSheet("" if has_i_ii else "color: transparent;")
        self.cb_cond.blockSignals(False)

        self.cb_method.blockSignals(True)
        self.cb_method.clear()
        self.cb_method.addItems(METHOD_OPTIONS.get(gost, []))
        self.cb_method.blockSignals(False)

        self._refresh_f()

    def _refresh_f(self):
        import json as _j
        try:
            with open("params.json", "r", encoding="utf-8") as fh:
                data = _j.load(fh)
        except (FileNotFoundError, ValueError):
            data = {}
        gost    = self.cb_std.currentText()
        p_key   = self.cb_load.currentText()
        i_ii    = self.cb_cond.currentText()
        opts    = GOST_OPTIONS.get(gost, {})
        visible = opts.get("fields", [])
        try:
            vals = data[gost][p_key][i_ii] if opts.get("i_ii") else data[gost][p_key]
        except KeyError:
            vals = {}
        _hide = "color: transparent; background: transparent; border-color: transparent;"
        for key, le in self._f_edits.items():
            show = key in visible
            le.setStyleSheet("" if show else _hide)
            le.setEnabled(show)
            self._f_labels[key].setStyleSheet("" if show else "color: transparent;")
            if show:
                v = vals.get(key) if vals else None
                le.setText(str(v) if v is not None else "")
            else:
                le.setText("")

    def _emit_params(self):
        self.params_changed.emit(self.cb_std.currentText(), self.cb_method.currentText())


