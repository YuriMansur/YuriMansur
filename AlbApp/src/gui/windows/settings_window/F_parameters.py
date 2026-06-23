from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import pyqtSignal

_SECTION_STYLE = "QFrame#section { border: 1px solid #555555; border-radius: 4px; }"

_TITLE_STYLE = "font-size: 15px; font-weight: bold; color: #9b59b6;"

import param_config

# Структура параметров (ГОСТы, уровни, условия, поля сил, поля стенда)
# вынесена в gost_config.json и читается через движок param_config.
FIELDS = param_config.f_fields()         # порядок определяет порядок отображения
STAND_FIELDS = param_config.stand_fields()


class FWindow(QWidget):
    saved = pyqtSignal()   # «Записать» нажата — параметры в файле обновлены

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(32)
        row_layout.setAlignment(__import__('PyQt6.QtCore', fromlist=['Qt']).Qt.AlignmentFlag.AlignTop)

        # ── Левая колонка: параметры F ──────────────────────────────────────
        content_frame = QFrame()
        content_frame.setObjectName("section")
        content_frame.setStyleSheet("QFrame#section { border: 1px solid #555555; border-radius: 4px; }")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(8, 8, 8, 8)

        lbl_params = QLabel("Параметры испытания")
        lbl_params.setStyleSheet(_TITLE_STYLE)
        content_layout.addWidget(lbl_params)

        self.combo_gost = QComboBox()
        self.combo_gost.addItems(param_config.gosts())

        self.combo_p = QComboBox()

        self.combo_I_II = QComboBox()

        self.combo_gost.currentTextChanged.connect(self.update_combo)
        self.combo_p.currentTextChanged.connect(self.update_combo)
        self.combo_I_II.currentTextChanged.connect(self.update_fields)

        self.form = QFormLayout()
        self.form.setVerticalSpacing(6)
        self.form.setHorizontalSpacing(8)
        self.inputs = {}
        for name in FIELDS:
            inp = QLineEdit()
            self.inputs[name] = inp
            self.form.addRow(f"{name}:", inp)
            lbl_widget = self.form.labelForField(inp)
            if lbl_widget:
                lbl_widget.setStyleSheet("color: #cccccc;")

        self._btn_write = QPushButton("Записать")
        self._btn_write.clicked.connect(self.save_params)

        content_layout.addWidget(self.combo_gost)
        content_layout.addWidget(self.combo_p)
        content_layout.addWidget(self.combo_I_II)
        content_layout.addLayout(self.form)
        content_layout.addWidget(self._btn_write)

        # ── Правая колонка: сведения о стенде ───────────────────────────────
        stand_frame = QFrame()
        stand_frame.setObjectName("section")
        stand_frame.setStyleSheet("QFrame#section { border: 1px solid #555555; border-radius: 4px; }")
        stand_layout = QVBoxLayout(stand_frame)
        stand_layout.setSpacing(8)
        stand_layout.setContentsMargins(8, 8, 8, 8)

        lbl_stand = QLabel("Параметры оборудования стенда")
        lbl_stand.setStyleSheet(_TITLE_STYLE)
        stand_layout.addWidget(lbl_stand)

        self.stand_form = QFormLayout()
        self.stand_form.setVerticalSpacing(6)
        self.stand_form.setHorizontalSpacing(8)
        self.stand_inputs = {}
        for label, key in STAND_FIELDS:
            inp = QLineEdit()
            self.stand_inputs[key] = inp
            self.stand_form.addRow(label, inp)
            lbl_widget = self.stand_form.labelForField(inp)
            if lbl_widget:
                lbl_widget.setStyleSheet("color: #cccccc;")

        self._btn_stand = QPushButton("Записать")
        self._btn_stand.clicked.connect(self.save_stand_info)

        stand_layout.addLayout(self.stand_form)
        stand_layout.addWidget(self._btn_stand)

        from PyQt6.QtCore import Qt as _Qt
        row_layout.addWidget(content_frame, 0, _Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(stand_frame,   0, _Qt.AlignmentFlag.AlignTop)

        layout.addLayout(row_layout)
        layout.addStretch()
        self._row_layout = row_layout

        # Заполняем combo_p и combo_I_II по первому ГОСТу при старте
        self._fill_combo_p(self.combo_gost.currentText())
        self.update_fields()
        self._load_stand_info()

    def _fill_combo_p(self, gost):
        # Заполняет combo_p (уровни) и combo_I_II (условия) исходя из ГОСТа
        self.combo_p.clear()
        self.combo_I_II.clear()
        self.combo_p.addItems(param_config.load_levels(gost))
        conds = param_config.conditions(gost)
        if conds:
            self.combo_I_II.addItems(conds)
            self.combo_I_II.show()
        else:
            self.combo_I_II.hide()

    def update_combo(self, text):
        # Обрабатывает изменение combo_gost и combo_p
        sender = self.sender()
        if sender == self.combo_gost:
            self._fill_combo_p(text)
        elif sender == self.combo_p:
            self.update_fields()

    def _get_values(self):
        # Читает параметры из файла для текущего выбора комбобоксов
        # Возвращает dict с параметрами или None если запись не найдена
        gost = self.combo_gost.currentText()
        p    = self.combo_p.currentText()
        i_ii = self.combo_I_II.currentText()
        return param_config.values(gost, p, i_ii)

    def update_fields(self):
        # Обновляет видимость и значения полей формы
        # Показывает только поля из gost_config.json (fields данного ГОСТа)
        gost = self.combo_gost.currentText()
        visible = param_config.fields(gost)
        values = self._get_values()

        for name, inp in self.inputs.items():
            row = self.form.getWidgetPosition(inp)[0]
            if name not in visible:
                self.form.setRowVisible(row, False)
                continue
            self.form.setRowVisible(row, True)
            val = values.get(name) if values else None
            inp.setText(str(val) if val is not None else "")

    def _read_file(self):
        # Читает params.json через движок (пустой dict если файла нет)
        return param_config.read_params()

    def save_params(self):
        # Сохраняет текущие значения полей в params.json
        # Пустое поле сохраняется как null чтобы не затирать исходные данные
        gost = self.combo_gost.currentText()
        p    = self.combo_p.currentText()
        i_ii = self.combo_I_II.currentText()
        fields = {name: (inp.text() if inp.text() != "" else None) for name, inp in self.inputs.items()}

        data = self._read_file()
        data.setdefault(gost, {})

        if i_ii:
            data[gost].setdefault(p, {})
            data[gost][p][i_ii] = fields
        else:
            data[gost][p] = fields

        param_config.write_params(data)
        self.saved.emit()

    def _load_stand_info(self):
        data = self._read_file().get("stand_info", {})
        for key, inp in self.stand_inputs.items():
            inp.setText(data.get(key, ""))

    def save_stand_info(self):
        data = self._read_file()
        data["stand_info"] = {key: inp.text() for key, inp in self.stand_inputs.items()}
        param_config.write_params(data)
        self.saved.emit()

    def set_theme(self, dark: bool):
        text   = "#ecf0f1" if dark else "#1a1a1a"
        muted  = "#cccccc" if dark else "#555555"
        border = "#555555" if dark else "#cccccc"
        bg     = "#2c2c2c" if dark else "#ffffff"
        btn_bg = "#3d3d3d" if dark else "#b0b0b0"
        btn_hover = "#4a4a4a" if dark else "#c8c8c8"
        btn_text = "#ecf0f1" if dark else "#1a1a1a"

        self.setStyleSheet(f"""
            QComboBox {{
                color: {text};
                background: {bg};
                border: 1px solid {border};
                border-radius: 3px;
                padding: 2px 6px;
            }}
            QLineEdit {{
                color: {text};
                background: {bg};
                border: 1px solid {border};
                border-radius: 3px;
                padding: 2px 6px;
            }}
            QPushButton {{
                background: {btn_bg};
                color: {btn_text};
                border-radius: 4px;
                min-height: 30px;
            }}
            QPushButton:hover {{ background: {btn_hover}; }}
        """)

        for form in (self.form, self.stand_form):
            for i in range(form.rowCount()):
                lbl = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
                if lbl and lbl.widget():
                    lbl.widget().setStyleSheet(f"color: {muted};")
