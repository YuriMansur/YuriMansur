from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QDateTimeEdit, QComboBox, QLineEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt, QDateTime, pyqtSignal

import param_config

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
            from gui.popups.pdf_reader import PdfReaderWidget
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

        _si = param_config.stand_info()

        self._stand_labels = {}   # key → QLabel значения (для перечитывания)
        for label, key in param_config.stand_fields():
            row = QHBoxLayout()
            row.setSpacing(10)
            lk = QLabel(label)
            lv = QLabel(_si.get(key, ""))
            self._stand_labels[key] = lv
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
        self.cb_std.addItems(param_config.gosts())
        form2.addRow("Стандарт проведения испытаний:", self.cb_std)

        self.cb_load = QComboBox()
        form2.addRow("Уровень нагружения:", self.cb_load)

        # Строка условия нужна не всем ГОСТам, но место под неё держим всегда,
        # иначе при смене ГОСТа всё ниже прыгает. Сама строка — в общей форме,
        # чтобы колонки совпадали с остальными (во вложенной форме своя ширина
        # подписей, и комбобокс получался шире прочих). Схлопывание скрытой
        # строки компенсирует заглушка ниже: retainSizeWhenHidden в QFormLayout
        # место не удерживает.
        self.cb_cond = QComboBox()
        self._lbl_cond = QLabel("Условие нагружения:")
        form2.addRow(self._lbl_cond, self.cb_cond)

        self._cond_gap = QLabel()
        self._cond_gap.setVisible(False)
        form2.addRow(self._cond_gap)

        # Поля сил живут в отдельной форме фиксированной высоты. Строки скрытых
        # полей схлопываются, поэтому видимые идут подряд, без пустых промежутков;
        # высота же блока рассчитана на ГОСТ с наибольшим числом полей, так что
        # при смене ГОСТа методика и всё, что ниже, остаются на месте.
        f_host = QWidget()
        self._form_f = QFormLayout(f_host)
        self._form_f.setContentsMargins(0, 0, 0, 0)
        self._form_f.setSpacing(4)
        self._form_f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        _F_KEYS = param_config.f_fields()
        self._f_edits  = {}
        self._f_labels = {}
        # Ширина поля — под число не длиннее пяти знаков; одинаковая у всех полей
        # и всех ГОСТов, поэтому колонка значений не «дышит» при переключении.
        for key in _F_KEYS:
            le  = QLineEdit(); le.setReadOnly(True)
            le.setFixedWidth(le.fontMetrics().horizontalAdvance("99999") + 24)
            lbl = QLabel(f"{key}:")
            self._f_edits[key]  = le
            self._f_labels[key] = lbl
            self._form_f.addRow(lbl, le)

        # высота = самый «широкий» ГОСТ; шаг строки считаем из формы со всеми
        # строками, они одинаковые — деление точное
        max_rows = max((len(param_config.fields(g)) for g in param_config.gosts()),
                       default=0)
        if _F_KEYS and max_rows:
            row_h = f_host.sizeHint().height() / len(_F_KEYS)
            f_host.setFixedHeight(round(row_h * max_rows))
        form2.addRow(f_host)

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
        # поля с Expanding-политикой растягиваются на ширину формы (Fusion по
        # умолчанию держит поля на sizeHint — иначе строка ввода короткая)
        form1.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # каждая строка: метка над полем, поле — на всю ширину формы
        def _full_row(label: str, widget):
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            form1.addRow(QLabel(label))
            form1.addRow(widget)

        self.le_sample_name = QLineEdit()
        self.le_sample_name.setPlaceholderText("Введите название")
        _full_row("Название образца:", self.le_sample_name)

        self._dt1 = QDateTimeEdit(QDateTime.currentDateTime())
        self._dt1.setDisplayFormat("dd.MM.yyyy"); self._dt1.setCalendarPopup(True)
        _full_row("Дата получения образца на:", self._dt1)

        self._dt2 = QDateTimeEdit(QDateTime.currentDateTime())
        self._dt2.setDisplayFormat("dd.MM.yyyy"); self._dt2.setCalendarPopup(True)
        _full_row("Дата проведения:", self._dt2)

        self._cb_used = QComboBox(); self._cb_used.addItems(["Нет", "Да"])
        _full_row("Образец используется:", self._cb_used)

        self._cb_replace = QComboBox(); self._cb_replace.addItems(["Нет", "Да"])
        _full_row("Образец используется взамен разрушенного:", self._cb_replace)

        self._le_clamp = QLineEdit(); self._le_clamp.setPlaceholderText("Введите значение")
        _full_row("Применяемые концевые крепления:", self._le_clamp)

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
        self.cb_load.blockSignals(True)
        self.cb_load.clear()
        self.cb_load.addItems(param_config.load_levels(gost))
        self.cb_load.blockSignals(False)

        conds = param_config.conditions(gost)
        has_cond = bool(conds)
        self.cb_cond.blockSignals(True)
        self.cb_cond.clear()
        if has_cond:
            self.cb_cond.addItems(conds)
        self.cb_cond.blockSignals(False)
        # нет условий у ГОСТа → виджеты скрыты, но место строки сохраняется
        # (retainSizeWhenHidden) — блок остаётся жёстким, ничего не прыгает
        self.cb_cond.setVisible(has_cond)
        self._lbl_cond.setVisible(has_cond)
        self._sync_cond_height()

        self.cb_method.blockSignals(True)
        self.cb_method.clear()
        self.cb_method.addItems(param_config.methods(gost))
        self.cb_method.blockSignals(False)

        self._refresh_f()

    def _sync_cond_height(self):
        """Держать место строки условия, когда её у ГОСТа нет.

        Заглушка показывается вместо скрытой строки и повторяет её высоту.
        Высоту берём у самого комбобокса: тему применяют позже
        (ExperimentWidget.set_theme задаёт комбобоксам свою высоту), поэтому
        зафиксировать её на старте нельзя — строка обрезалась бы.
        """
        # isVisibleTo, а не isVisible: на старте виджет ещё не показан, и
        # isVisible() дал бы False даже для строки, которая должна быть видна
        hidden = not self.cb_cond.isVisibleTo(self)
        if hidden:
            h = max(self.cb_cond.minimumHeight(), self.cb_cond.sizeHint().height(),
                    self._lbl_cond.sizeHint().height())
            self._cond_gap.setFixedHeight(h)
        self._cond_gap.setVisible(hidden)

    def _refresh_f(self):
        gost    = self.cb_std.currentText()
        p_key   = self.cb_load.currentText()
        i_ii    = self.cb_cond.currentText() if param_config.has_conditions(gost) else ""
        visible = param_config.fields(gost)
        vals    = param_config.values(gost, p_key, i_ii) or {}
        for key, le in self._f_edits.items():
            show = key in visible
            row = self._form_f.getWidgetPosition(le)[0]
            if row >= 0:
                self._form_f.setRowVisible(row, show)   # строка убирается целиком
            if show:
                v = vals.get(key) if vals else None
                le.setText(str(v) if v is not None else "")
            else:
                le.setText("")

    def _emit_params(self):
        self.params_changed.emit(self.cb_std.currentText(), self.cb_method.currentText())

    def reload_params(self):
        """Перечитать параметры из файла (после «Записать» в настройках):
        сведения о стенде + значения сил для текущего выбора."""
        si = param_config.stand_info()
        for key, lbl in self._stand_labels.items():
            lbl.setText(si.get(key, ""))
        self._refresh_f()

    def sample_info(self) -> dict:
        """Данные блока «Информация об исследуемом образце» — для протокола."""
        return {
            "sample_name":      self.le_sample_name.text(),
            "date_received":    self._dt1.dateTime().toString("dd.MM.yyyy"),
            "date_conducted":   self._dt2.dateTime().toString("dd.MM.yyyy"),
            "used":             self._cb_used.currentText(),
            "used_replacement": self._cb_replace.currentText(),
            "clamps":           self._le_clamp.text(),
        }


