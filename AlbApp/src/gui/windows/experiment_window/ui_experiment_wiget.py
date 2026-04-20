from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QFormLayout, QDateTimeEdit, QComboBox, QLineEdit, QScrollArea,
    QPushButton, QSpinBox, QSlider, QFileDialog, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt, QDateTime, QTimer
from PyQt6.QtGui import QImage, QPixmap
import pyqtgraph as pg
import datetime, os

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None

pg.setConfigOptions(antialias=True)

_CHART_TITLES = ["Канал 1", "Канал 2", "Канал 3"]
_CH_COLORS    = ["#e67e22", "#3498db", "#2ecc71"]

_FRAME_STYLE = """
    QFrame {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(26, 188, 156, 0.3);
        border-radius: 6px;
    }
"""

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


def _make_plot(title: str, color: str) -> pg.PlotWidget:
    pw = pg.PlotWidget()
    pw.setBackground("#1a252f")
    pw.showGrid(x=True, y=True, alpha=0.25)
    pw.setMinimumHeight(120)
    pi = pw.getPlotItem()
    pi.setTitle(title, color="#ecf0f1", size="10pt")
    pi.getAxis("bottom").setPen(pg.mkPen("#4a6278"))
    pi.getAxis("left")  .setPen(pg.mkPen("#4a6278"))
    pi.getAxis("bottom").setTextPen(pg.mkPen("#7f8c8d"))
    pi.getAxis("left")  .setTextPen(pg.mkPen("#7f8c8d"))
    pw.plot([], [], pen=pg.mkPen(color, width=1.5))
    return pw


class _CameraWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap      = None
        self._writer   = None
        self._recording = False
        self._timer    = QTimer(self)
        self._timer.timeout.connect(self._grab_frame)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # заголовок секции камеры
        title = QLabel("Камера")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1abc9c; background: transparent; border: none;")
        lay.addWidget(title)

        # превью
        self._preview = QLabel("Нет сигнала")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from PyQt6.QtWidgets import QSizePolicy
        self._preview.setMinimumSize(520, 520)
        self._preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview.setStyleSheet("""
            QLabel {
                background: #0d1a24;
                color: #4a6278;
                border: 1px solid #4a6278;
                border-radius: 4px;
                font-size: 13px;
            }
        """)
        lay.addWidget(self._preview)

        # строка: выбор камеры + кнопки
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self._cb_cam = QComboBox()
        self._cb_cam.setStyleSheet("""
            QComboBox {
                background: #2c3e50; color: #ecf0f1;
                border: 1px solid #4a6278; border-radius: 3px;
                padding: 3px 6px; min-height: 24px; font-size: 12px;
            }
        """)
        for idx in range(4):
            self._cb_cam.addItem(f"Камера {idx}")
        ctrl_row.addWidget(self._cb_cam, 1)

        self._btn_open = QPushButton("▶ Открыть")
        self._btn_rec  = QPushButton("⏺ Запись")
        self._btn_stop = QPushButton("⏹ Стоп")
        self._btn_rec .setEnabled(False)
        self._btn_stop.setEnabled(False)

        _btn_style = """
            QPushButton {
                background: #3d5166; color: #ecf0f1;
                border: 1px solid #4a6278; border-radius: 3px;
                padding: 4px 10px; min-height: 24px; font-size: 12px;
            }
            QPushButton:hover   { background: #4a6a82; }
            QPushButton:pressed { background: #2980b9; }
            QPushButton:disabled { background: #2a3a4a; color: #5a6a7a; }
        """
        for btn in (self._btn_open, self._btn_rec, self._btn_stop):
            btn.setStyleSheet(_btn_style)
            ctrl_row.addWidget(btn)

        lay.addLayout(ctrl_row)

        # статус
        self._lbl_status = QLabel("Камера закрыта")
        self._lbl_status.setStyleSheet("font-size: 11px; color: #7f8c8d; background: transparent; border: none;")
        lay.addWidget(self._lbl_status)

        self._btn_open.clicked.connect(self._open_camera)
        self._btn_rec .clicked.connect(self._start_record)
        self._btn_stop.clicked.connect(self._stop)

    def _open_camera(self):
        if _cv2 is None:
            self._lbl_status.setText("opencv-python не установлен")
            return
        idx = self._cb_cam.currentIndex()
        if self._cap:
            self._cap.release()
        self._cap = _cv2.VideoCapture(idx, _cv2.CAP_DSHOW)
        if self._cap.isOpened():
            self._timer.start(33)
            self._btn_rec.setEnabled(True)
            self._btn_stop.setEnabled(True)
            self._lbl_status.setStyleSheet("font-size: 11px; color: #2ecc71; background: transparent; border: none;")
            self._lbl_status.setText("Камера открыта")
        else:
            self._lbl_status.setStyleSheet("font-size: 11px; color: #e74c3c; background: transparent; border: none;")
            self._lbl_status.setText(f"Камера {idx} недоступна")

    def _start_record(self):
        if not self._cap or not self._cap.isOpened():
            return
        w = int(self._cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.expanduser("~"), f"rec_{ts}.avi")
        fourcc = _cv2.VideoWriter_fourcc(*"XVID")
        self._writer = _cv2.VideoWriter(path, fourcc, 25.0, (w, h))
        self._recording = True
        self._btn_rec.setEnabled(False)
        self._lbl_status.setStyleSheet("font-size: 11px; color: #e74c3c; background: transparent; border: none;")
        self._lbl_status.setText(f"● Запись → {os.path.basename(path)}")

    def _stop(self):
        self._recording = False
        self._timer.stop()
        if self._writer:
            self._writer.release()
            self._writer = None
        if self._cap:
            self._cap.release()
            self._cap = None
        self._preview.setPixmap(QPixmap())
        self._preview.setText("Нет сигнала")
        self._btn_rec.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._lbl_status.setStyleSheet("font-size: 11px; color: #7f8c8d; background: transparent; border: none;")
        self._lbl_status.setText("Камера закрыта")

    def _grab_frame(self):
        if not self._cap:
            return
        ok, frame = self._cap.read()
        if not ok:
            return
        if self._recording and self._writer:
            self._writer.write(frame)
        rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self._preview.width(), self._preview.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(pix)

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)


_SEC1_STYLE = """
    QWidget  { background: transparent; }
    QLabel   { color: #ecf0f1; font-size: 12px; background: transparent; border: none; }
    QLineEdit {
        background: #2c3e50; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 3px;
        padding: 3px 6px; min-height: 22px; font-size: 12px;
    }
    QPushButton {
        background: #3d5166; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 3px;
        padding: 4px 12px; min-height: 24px; font-size: 12px;
    }
    QPushButton:hover   { background: #4a6a82; }
    QPushButton:pressed { background: #2980b9; }
    QSlider::groove:horizontal { background: #4a6278; height: 4px; border-radius: 2px; }
    QSlider::handle:horizontal {
        background: #3498db; width: 12px; height: 12px;
        margin: -4px 0; border-radius: 6px; border: none;
    }
    QDoubleSpinBox, QSpinBox {
        background: #2c3e50; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 3px;
        padding: 2px 4px; min-height: 22px; font-size: 12px;
    }
"""


def _led(color: str = "#2ecc71") -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(20, 20)
    lbl.setStyleSheet(f"""
        QLabel {{
            background-color: {color};
            border-radius: 10px;
            border: 1px solid rgba(0,0,0,0.4);
        }}
    """)
    return lbl


def _make_section1() -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    container = QWidget()
    container.setStyleSheet(_SEC1_STYLE)
    lay = QVBoxLayout(container)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.setSpacing(8)

    # заголовок
    title = QLabel("Параметры оборудования стенда")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ecf0f1; background: transparent; border: none;")
    title.setWordWrap(True)
    lay.addWidget(title)

    # файл
    file_row = QHBoxLayout()
    file_col = QVBoxLayout()
    file_col.setSpacing(2)
    file_col.addWidget(QLabel("Файл"))
    le_file = QLineEdit()
    le_file.setPlaceholderText("Путь к файлу...")
    btn_browse = QPushButton("...")
    btn_browse.setFixedWidth(28)
    btn_browse.clicked.connect(lambda: le_file.setText(
        QFileDialog.getOpenFileName(container, "Выберите файл")[0]))
    f_input_row = QHBoxLayout()
    f_input_row.addWidget(le_file)
    f_input_row.addWidget(btn_browse)
    file_col.addLayout(f_input_row)
    file_row.addLayout(file_col, 1)

    read_col = QVBoxLayout()
    read_col.setSpacing(2)
    read_col.addWidget(QLabel("Считать из файла"))
    read_col.addWidget(QPushButton("Считать"))
    file_row.addLayout(read_col)
    lay.addLayout(file_row)

    # форма параметров
    sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setStyleSheet("QFrame { color: #4a6278; }")
    lay.addWidget(sep1)

    form = QFormLayout()
    form.setSpacing(6)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    fields = [
        ("Марка и модель стенда:",  "Стенд линейных испытаний"),
        ("Серийный номер стенда:",  "НРО.233.112"),
        ("Дата аттестации стенда:", "15.12.2023"),
        ("Марка и модель СИ 1:",    "DEE-01.459"),
        ("Марка и модель СИ 2:",    ""),
    ]
    for label, default in fields:
        le = QLineEdit(default)
        form.addRow(label, le)
    lay.addLayout(form)

    sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("QFrame { color: #4a6278; }")
    lay.addWidget(sep2)

    # Питание двигателя
    row_power = QHBoxLayout()
    row_power.addWidget(QLabel("Питание двигателя"))
    row_power.addWidget(QPushButton("Включить"))
    row_power.addStretch()
    alarm_col = QVBoxLayout()
    alarm_col.setSpacing(2)
    alarm_lbl = QLabel("АВАРИЯ")
    alarm_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    alarm_lbl.setStyleSheet("font-size: 10px; color: #ecf0f1; background: transparent; border: none;")
    alarm_col.addWidget(alarm_lbl)
    alarm_col.addWidget(_led("#2ecc71"), 0, Qt.AlignmentFlag.AlignHCenter)
    row_power.addLayout(alarm_col)
    reset_col = QVBoxLayout()
    reset_col.setSpacing(2)
    reset_lbl = QLabel("Сброс")
    reset_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    reset_lbl.setStyleSheet("font-size: 10px; color: #ecf0f1; background: transparent; border: none;")
    reset_col.addWidget(reset_lbl)
    reset_col.addWidget(QPushButton("Сброс"))
    row_power.addLayout(reset_col)
    lay.addLayout(row_power)

    # Ручное вращение
    row_manual = QHBoxLayout()
    row_manual.addWidget(QLabel("Ручное вращение"))
    row_manual.addWidget(QPushButton("Включить"))
    row_manual.addStretch()
    lay.addLayout(row_manual)

    # Вверх
    row_up = QHBoxLayout()
    row_up.addWidget(QLabel("Вверх"))
    row_up.addWidget(QPushButton("Включить"))
    row_up.addStretch()
    lay.addLayout(row_up)

    # Скорость
    speed_lbl = QLabel("Скорость мм/сек")
    speed_lbl.setStyleSheet("font-size: 11px; color: #7f8c8d; background: transparent; border: none;")
    lay.addWidget(speed_lbl)
    speed_row = QHBoxLayout()
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 800)
    slider.setValue(1)
    spin_speed = QDoubleSpinBox()
    spin_speed.setRange(0.0, 8.0)
    spin_speed.setSingleStep(0.01)
    spin_speed.setDecimals(2)
    spin_speed.setValue(0.01)
    spin_speed.setFixedWidth(64)
    slider.valueChanged.connect(lambda v: spin_speed.setValue(v / 100))
    spin_speed.valueChanged.connect(lambda v: slider.setValue(int(v * 100)))
    speed_row.addWidget(slider, 1)
    speed_row.addWidget(spin_speed)
    lay.addLayout(speed_row)

    # Вниз
    row_down = QHBoxLayout()
    row_down.addWidget(QLabel("Вниз"))
    row_down.addWidget(QPushButton("Включить"))
    row_down.addStretch()
    lay.addLayout(row_down)

    sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
    sep3.setStyleSheet("QFrame { color: #4a6278; }")
    lay.addWidget(sep3)

    # Текущая позиция
    pos_row = QHBoxLayout()
    pos_col = QVBoxLayout()
    pos_col.addWidget(QLabel("Текущая позиция"))
    le_pos = QLineEdit("0"); le_pos.setReadOnly(True)
    pos_col.addWidget(le_pos)
    pos_row.addLayout(pos_col)
    pos_row.addStretch()
    zero_col = QVBoxLayout()
    zero_col.addWidget(QLabel("Записать нулевое положение"))
    zero_col.addWidget(QPushButton("Записать"))
    pos_row.addLayout(zero_col)
    lay.addLayout(pos_row)

    # Нагрузка
    load_row = QHBoxLayout()
    load_col = QVBoxLayout()
    load_col.addWidget(QLabel("Нагрузка, Н"))
    le_load = QLineEdit("0"); le_load.setReadOnly(True)
    load_col.addWidget(le_load)
    load_row.addLayout(load_col)
    load_row.addStretch()
    zero_h_col = QVBoxLayout()
    zero_h_col.addWidget(QLabel("Записать нулевое положение Н"))
    zero_h_col.addWidget(QPushButton("Записать"))
    load_row.addLayout(zero_h_col)
    load_row.addStretch()
    dh_col = QVBoxLayout()
    dh_col.addWidget(QLabel("dH, sec 2"))
    dh_spin = QSpinBox(); dh_spin.setRange(0, 9999); dh_spin.setValue(0)
    dh_col.addWidget(dh_spin)
    load_row.addLayout(dh_col)
    lay.addLayout(load_row)

    lay.addStretch()
    scroll.setWidget(container)
    return scroll


def _make_section2() -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    container = QWidget()
    container.setStyleSheet(_FORM_STYLE + "QWidget { background: transparent; }")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(12)

    # ── блок 1: Информация об образце ────────────────────────────────────────
    grp1 = _group_box("Информация об исследуемом образце", layout)
    form1 = QFormLayout()
    form1.setSpacing(8)
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

    # ── блок 2: Параметры испытания ──────────────────────────────────────────
    grp2 = _group_box("Параметры испытания", layout)
    form2 = QFormLayout()
    form2.setSpacing(8)
    form2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    cb_std = QComboBox()
    cb_std.addItems(["ГОСТ Р 53868", "ГОСТ 27.002", "ISO 6892"])
    form2.addRow("Стандарт проведения испытаний:", cb_std)

    cb_load = QComboBox()
    cb_load.addItems(["P1", "P2", "P3"])
    cb_load.setCurrentText("P2")
    form2.addRow("Уровень Нагружения:", cb_load)

    cb_cond = QComboBox()
    cb_cond.addItems(["1", "2", "3"])
    cb_cond.setCurrentText("2")
    form2.addRow("Условие нагружения:", cb_cond)

    lbl_err = QLabel("Отсутствуют значения в базе данных.\nПроверьте правильность параметров.")
    lbl_err.setStyleSheet("color: #e74c3c; font-size: 11px; background: transparent; border: none;")
    lbl_err.setWordWrap(True)
    form2.addRow("", lbl_err)

    cb_method = QComboBox()
    cb_method.addItems(["16.2.2+С", "16.2.2", "16.2.3"])
    form2.addRow("Методика:", cb_method)

    grp2.addLayout(form2)

    # ── блок 3: Камера ───────────────────────────────────────────────────────
    sep_cam = QFrame(); sep_cam.setFrameShape(QFrame.Shape.HLine)
    sep_cam.setStyleSheet("QFrame { color: #4a6278; background: #4a6278; }")
    layout.addWidget(sep_cam)
    layout.addWidget(_CameraWidget())

    layout.addStretch()
    scroll.setWidget(container)
    return scroll


def _make_section3() -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    container = QWidget()
    container.setStyleSheet("""
        QWidget { background: transparent; }
        QLabel  { color: #ecf0f1; font-size: 12px; background: transparent; border: none; }
        QPushButton {
            background: #3d5166; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 3px;
            padding: 4px 12px; min-height: 24px; font-size: 12px;
        }
        QPushButton:hover  { background: #4a6a82; }
        QPushButton:pressed { background: #2980b9; }
        QComboBox {
            background: #2c3e50; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 3px;
            padding: 3px 6px; min-height: 22px; font-size: 12px;
        }
        QSpinBox {
            background: #2c3e50; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 3px;
            padding: 3px 6px; min-height: 22px; font-size: 12px; min-width: 60px;
        }
    """)
    lay = QVBoxLayout(container)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.setSpacing(10)

    def _orange(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #e67e22; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        lbl.setWordWrap(True)
        return lbl

    def _btn(text: str) -> QPushButton:
        return QPushButton(text)

    def _step(num: str, desc: str, btn_text: str) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(_orange(f"{num}."))
        lbl = QLabel(desc)
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        lay.addLayout(row)
        lay.addWidget(_btn(btn_text))

    # заголовок
    title_lbl = QLabel("16.2.2  Основное статическое испытание")
    title_lbl.setStyleSheet("color: #e67e22; font-size: 13px; font-weight: bold; background: transparent; border: none;")
    title_lbl.setWordWrap(True)
    lay.addWidget(title_lbl)

    # подзаголовок
    sub = QLabel("Установите образец")
    sub.setStyleSheet("color: #1abc9c; font-size: 13px; font-weight: bold; background: transparent; border: none;")
    lay.addWidget(sub)

    # инструкция
    info = QLabel("· Зарегистрировать условие нагружения и уровень нагрузки, значения")
    info.setWordWrap(True)
    lay.addWidget(info)

    # кнопка F=0 + поле значения
    row_f0 = QHBoxLayout()
    row_f0.addWidget(_btn("F=0"))
    spin_f = QSpinBox(); spin_f.setRange(-99999, 99999); spin_f.setValue(0)
    row_f0.addWidget(spin_f)
    row_f0.addStretch()
    lay.addLayout(row_f0)

    # Специальное приспособление
    lay.addWidget(QLabel("Специальное приспособление 2"))
    cb_fixture = QComboBox()
    cb_fixture.addItems(["", "Приспособление A", "Приспособление B"])
    lay.addWidget(cb_fixture)

    _step("4", "t = не менее 10с и не более 30с", "Fset")
    _step("5", "t = не менее 10 мин и не более 20 мин", "F=0")

    lay.addWidget(_orange("6."))
    lay.addWidget(_btn("Fstab"))

    lay.addWidget(_orange("8.  Обнулить 2"))
    lay.addWidget(_btn("Записать"))

    lay.addWidget(_orange("5."))
    lay.addWidget(_btn("Fsu upper"))

    # Записать L1
    lay.addWidget(QLabel("Записать L1"))
    row_l1 = QHBoxLayout()
    row_l1.addWidget(_btn("Записать"))
    lbl_l1 = QLabel("L1")
    row_l1.addWidget(lbl_l1)
    spin_l1 = QSpinBox(); spin_l1.setRange(-99999, 99999); spin_l1.setValue(0)
    row_l1.addWidget(spin_l1)
    row_l1.addStretch()
    lay.addLayout(row_l1)

    lay.addStretch()

    # кнопка внизу
    btn_protocol = QPushButton("Сформировать Протокол")
    btn_protocol.setStyleSheet("""
        QPushButton {
            background: #2c3e50; color: #ecf0f1;
            border: 2px solid #1abc9c; border-radius: 4px;
            padding: 10px; font-size: 14px; font-weight: bold;
        }
        QPushButton:hover  { background: #1abc9c; color: #1a252f; }
        QPushButton:pressed { background: #17a589; }
    """)
    lay.addWidget(btn_protocol)

    scroll.setWidget(container)
    return scroll


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
    inner.setContentsMargins(8, 0, 0, 0)
    parent_layout.addLayout(inner)
    return inner


class ExperimentWidget(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        header = QLabel("Испытание")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1abc9c;
                padding: 20px;
                background-color: rgba(26, 188, 156, 0.1);
            }
        """)
        main_layout.addWidget(header)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(6)

        for i in range(1, 5):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet(_FRAME_STYLE)
            col_layout = QVBoxLayout(frame)
            col_layout.setContentsMargins(8, 8, 8, 8)
            col_layout.setSpacing(4)


            if i == 1:
                col_layout.addWidget(_make_section1(), 1)
            elif i == 2:
                col_layout.addWidget(_make_section2(), 1)
            elif i == 3:
                col_layout.addWidget(_make_section3(), 1)
            elif i == 4:
                for ch_title, ch_color in zip(_CHART_TITLES, _CH_COLORS):
                    col_layout.addWidget(_make_plot(ch_title, ch_color), 1)
            else:
                col_layout.addStretch()

            columns_layout.addWidget(frame, 1)

        main_layout.addLayout(columns_layout, 1)
