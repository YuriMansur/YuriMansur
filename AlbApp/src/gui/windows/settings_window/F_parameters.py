from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
)
import json

# Все поля формы — порядок определяет порядок отображения
FIELDS = ["Fstab", "Fset", "Fsp", "F_su_lower_level", "F_su_upper_level"]

# Настройки для каждого ГОСТа:
#   items  — список методик в combo_p
#   i_ii   — нужен ли выбор нагружения I/II (False для А-режимов)
#   fields — какие поля формы показывать для этого ГОСТа
STAND_FIELDS = [
    ("Марка и модель стенда:",  "stand_model"),
    ("Серийный номер стенда:",  "stand_serial"),
    ("Дата аттестации стенда:", "stand_date"),
    ("Марка и модель СИ 1:",   "si1_model"),
    ("Марка и модель СИ 2:",   "si2_model"),
]

GOST_OPTIONS = {
    "Р53868-2021": {
        "items": ["P1", "P2"],
        "i_ii": True,
        "fields": ["Fstab", "F_su_lower_level", "F_su_upper_level"],
    },
    "Р ИСО 10328-2021": {
        "items": ["P3", "P4", "P5", "P6", "P7", "P8"],
        "i_ii": True,
        "fields": ["Fstab", "Fset", "Fsp", "F_su_lower_level", "F_su_upper_level"],
    },
    "Р ИСО 15032-2001": {
        "items": ["A60", "A80", "A100"],
        "i_ii": False,
        "fields": ["Fstab", "Fset", "Fsp", "F_su_lower_level", "F_su_upper_level"],
    },
}


class FWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(16)

        # ── Левая колонка: параметры F ──────────────────────────────────────
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)
        content_layout.setContentsMargins(8, 8, 8, 8)

        self.combo_gost = QComboBox()
        self.combo_gost.addItems(GOST_OPTIONS.keys())

        self.combo_p = QComboBox()

        self.combo_I_II = QComboBox()

        self.combo_gost.currentTextChanged.connect(self.update_combo)
        self.combo_p.currentTextChanged.connect(self.update_combo)
        self.combo_I_II.currentTextChanged.connect(self.update_fields)

        self.form = QFormLayout()
        self.form.setVerticalSpacing(3)
        self.form.setHorizontalSpacing(6)
        self.inputs = {}
        for name in FIELDS:
            inp = QLineEdit()
            self.inputs[name] = inp
            self.form.addRow(f"{name}:", inp)

        button_write = QPushButton("Записать")
        button_write.clicked.connect(self.save_params)

        content_layout.addWidget(self.combo_gost)
        content_layout.addWidget(self.combo_p)
        content_layout.addWidget(self.combo_I_II)
        content_layout.addLayout(self.form)
        content_layout.addWidget(button_write)
        content_layout.addStretch()

        # ── Правая колонка: сведения о стенде ───────────────────────────────
        stand_layout = QVBoxLayout()
        stand_layout.setSpacing(4)
        stand_layout.setContentsMargins(8, 8, 8, 8)

        self.stand_form = QFormLayout()
        self.stand_form.setVerticalSpacing(3)
        self.stand_form.setHorizontalSpacing(6)
        self.stand_inputs = {}
        for label, key in STAND_FIELDS:
            inp = QLineEdit()
            self.stand_inputs[key] = inp
            self.stand_form.addRow(label, inp)

        button_stand = QPushButton("Записать")
        button_stand.clicked.connect(self.save_stand_info)

        stand_layout.addLayout(self.stand_form)
        stand_layout.addWidget(button_stand)
        stand_layout.addStretch()

        row_layout.addLayout(content_layout)
        row_layout.addLayout(stand_layout)

        layout.addLayout(row_layout)

        # Заполняем combo_p и combo_I_II по первому ГОСТу при старте
        self._fill_combo_p(self.combo_gost.currentText())
        self.update_fields()
        self._load_stand_info()

    def _fill_combo_p(self, gost):
        # Заполняет combo_p и combo_I_II исходя из выбранного ГОСТа
        opts = GOST_OPTIONS.get(gost, {})
        self.combo_p.clear()
        self.combo_I_II.clear()
        self.combo_p.addItems(opts.get("items", []))
        if opts.get("i_ii"):
            self.combo_I_II.addItems(["I", "II"])
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
        data = self._read_file()
        try:
            return data[gost][p][i_ii] if i_ii else data[gost][p]
        except KeyError:
            return None

    def update_fields(self):
        # Обновляет видимость и значения полей формы
        # Показывает только поля из GOST_OPTIONS[gost]["fields"]
        gost = self.combo_gost.currentText()
        visible = GOST_OPTIONS[gost]["fields"]
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
        # Читает params.json, возвращает пустой dict если файл не найден
        try:
            with open("params.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

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

        with open("params.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_stand_info(self):
        data = self._read_file().get("stand_info", {})
        for key, inp in self.stand_inputs.items():
            inp.setText(data.get(key, ""))

    def save_stand_info(self):
        data = self._read_file()
        data["stand_info"] = {key: inp.text() for key, inp in self.stand_inputs.items()}
        with open("params.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
