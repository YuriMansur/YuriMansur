from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFormLayout,
    QDateTimeEdit, QComboBox, QLineEdit, QPushButton,
)
from PyQt6.QtCore import Qt, QDateTime

from gui.windows.settings_window.F_parameters import GOST_OPTIONS

_FORM_STYLE = """
    QLabel {
        color: #ecf0f1;
        font-size: 12px;
        background: transparent;
        border: none;
    }
    QDateTimeEdit, QComboBox, QLineEdit {
        background: #2c3e50;
        color: #ecf0f1;
        border: 1px solid #4a6278;
        border-radius: 3px;
        padding: 3px 6px;
        min-height: 22px;
        font-size: 12px;
    }
    QDateTimeEdit::drop-down, QComboBox::drop-down {
        border: none;
        background: #3d5166;
        width: 18px;
    }
    QComboBox QAbstractItemView {
        background: #2c3e50;
        color: #ecf0f1;
        selection-background-color: #3498db;
    }
"""


def _group_box(title: str, parent_layout: QVBoxLayout) -> QVBoxLayout:
    lbl = QLabel(title)
    lbl.setStyleSheet("""
        QLabel {
            font-size: 13px;
            font-weight: bold;
            color: #1abc9c;
            background: transparent;
            border: none;
            padding: 2px 0;
        }
    """)
    parent_layout.addWidget(lbl)
    inner = QVBoxLayout()
    inner.setContentsMargins(8, 0, 0, 4)
    inner.setSpacing(3)
    parent_layout.addLayout(inner)
    return inner


def _make_section2() -> QWidget:
    from PyQt6.QtWidgets import QSizePolicy as _SP

    wrapper = QWidget()
    wrapper.setStyleSheet("QWidget { background: transparent; }")
    wrapper_layout = QVBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.setSpacing(4)

    container = QWidget()
    container.setStyleSheet(_FORM_STYLE + "QWidget { background: transparent; }")
    container.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Preferred)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(4)

    # ── Параметры испытания ──────────────────────────────────────────────────
    grp2 = _group_box("Параметры испытания", layout)
    form2 = QFormLayout()
    form2.setSpacing(4)
    form2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    cb_std = QComboBox()
    cb_std.addItems(GOST_OPTIONS.keys())
    form2.addRow("Стандарт проведения испытаний:", cb_std)

    cb_load = QComboBox()
    form2.addRow("Уровень нагружения:", cb_load)

    cb_cond = QComboBox()
    form2.addRow("Условие нагружения:", cb_cond)

    def _fill_load(gost):
        opts = GOST_OPTIONS.get(gost, {})
        cb_load.blockSignals(True)
        cb_load.clear()
        cb_load.addItems(opts.get("items", []))
        cb_load.blockSignals(False)
        cb_cond.blockSignals(True)
        cb_cond.clear()
        if opts.get("i_ii"):
            cb_cond.addItems(["I", "II"])
            cb_cond.show()
        else:
            cb_cond.hide()
        cb_cond.blockSignals(False)
        _refresh_f()

    cb_method = QComboBox()
    cb_method.addItems(["13.2.1.2","16.2.1","16.2.2","16.2.2+С","16.2.3","17.3","17.4.3","17.4.4"])
    form2.addRow("Методика:", cb_method)

    _F_KEYS = ["Fstab", "Fset", "Fsp", "F_su_lower_level", "F_su_upper_level"]
    _f_edits = {}
    _f_rows  = {}
    for key in _F_KEYS:
        le = QLineEdit()
        le.setReadOnly(True)
        _f_rows[key] = form2.rowCount()
        _f_edits[key] = le
        form2.addRow(f"{key}:", le)

    def _refresh_f():
        import json as _j
        try:
            with open("params.json", "r", encoding="utf-8") as _fh:
                _data = _j.load(_fh)
        except (FileNotFoundError, ValueError):
            _data = {}
        gost_key = cb_std.currentText()
        p_key    = cb_load.currentText()
        i_ii     = cb_cond.currentText()
        opts     = GOST_OPTIONS.get(gost_key, {})
        visible  = opts.get("fields", [])
        try:
            vals = _data[gost_key][p_key][i_ii] if opts.get("i_ii") else _data[gost_key][p_key]
        except KeyError:
            vals = {}
        for key, le in _f_edits.items():
            form2.setRowVisible(_f_rows[key], key in visible)
            v = vals.get(key) if vals else None
            le.setText(str(v) if v is not None else "")

    cb_std.currentTextChanged.connect(_fill_load)
    cb_load.currentTextChanged.connect(lambda _: _refresh_f())
    cb_cond.currentTextChanged.connect(lambda _: _refresh_f())
    _fill_load(cb_std.currentText())

    grp2.addLayout(form2)

    # ── Информация об образце ────────────────────────────────────────────────
    grp1 = _group_box("Информация об исследуемом образце", layout)
    form1 = QFormLayout()
    form1.setSpacing(4)
    form1.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    dt1 = QDateTimeEdit(QDateTime.currentDateTime())
    dt1.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
    dt1.setCalendarPopup(True)
    form1.addRow("Дата получения образца на:", dt1)

    dt2 = QDateTimeEdit(QDateTime.currentDateTime())
    dt2.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
    dt2.setCalendarPopup(True)
    form1.addRow("Дата проведения:", dt2)

    cb_used = QComboBox()
    cb_used.addItems(["", "Да", "Нет"])
    form1.addRow("Образец используется:", cb_used)

    cb_replace = QComboBox()
    cb_replace.addItems(["", "Да", "Нет"])
    form1.addRow("Образец используется взамен\nразрушенного:", cb_replace)

    le_clamp = QLineEdit()
    le_clamp.setPlaceholderText("Введите значение")
    form1.addRow("Применяемые концевые крепления:", le_clamp)

    grp1.addLayout(form1)

    layout.addStretch()
    wrapper_layout.addWidget(container)
    wrapper_layout.addStretch()

    return wrapper
