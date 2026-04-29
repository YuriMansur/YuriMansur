import datetime, os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSlider,
    QComboBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None

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


class _CameraWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap       = None
        self._writer    = None
        self._recording = False
        self._timer     = QTimer(self)
        self._timer.timeout.connect(self._grab_frame)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        title = QLabel("Камера")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1abc9c; background: transparent; border: none;")
        lay.addWidget(title)

        self._preview = QLabel("Нет сигнала")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedHeight(240)
        self._preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._preview.setStyleSheet("""
            QLabel {
                background: #0d1a24; color: #4a6278;
                border: 1px solid #4a6278; border-radius: 4px; font-size: 13px;
            }
        """)
        lay.addWidget(self._preview, 1)

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
        ctrl_row.addWidget(self._cb_cam, 1)

        self._btn_open = QPushButton("▶ Открыть")
        self._btn_rec  = QPushButton("⏺ Запись")
        self._btn_stop = QPushButton("⏹ Стоп")
        self._btn_rec.setEnabled(False)
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

        self._lbl_status = QLabel("Камера закрыта")
        self._lbl_status.setStyleSheet("font-size: 11px; color: #7f8c8d; background: transparent; border: none;")
        lay.addWidget(self._lbl_status)

        self._btn_open.clicked.connect(self._open_camera)
        self._btn_rec.clicked.connect(self._start_record)
        self._btn_stop.clicked.connect(self._stop)
        self._populate_cameras()

    def _populate_cameras(self):
        self._cb_cam.clear()
        if _cv2 is None:
            self._cb_cam.addItem("opencv не установлен")
            return
        self._cb_cam.addItem("Поиск камер…")
        self._cb_cam.setEnabled(False)
        self._btn_open.setEnabled(False)

        class _Scanner(QThread):
            done = pyqtSignal(list)
            def run(self):
                names = []
                try:
                    import subprocess
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "Get-PnpDevice -Class Camera -Status OK | "
                         "Sort-Object InstanceId | "
                         "Select-Object -ExpandProperty FriendlyName"],
                        capture_output=True, text=True, timeout=5,
                    )
                    names = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                except Exception:
                    pass
                found = []
                cam_idx = 0
                for idx in range(6):
                    cap = _cv2.VideoCapture(idx, _cv2.CAP_DSHOW)
                    if cap.isOpened():
                        cap.release()
                        label = names[cam_idx] if cam_idx < len(names) else f"Устройство {idx}"
                        found.append((idx, label))
                        cam_idx += 1
                self.done.emit(found)

        self._scanner = _Scanner()
        self._scanner.done.connect(self._on_cameras_found)
        self._scanner.start()

    def _on_cameras_found(self, found: list):
        self._cb_cam.clear()
        if not found:
            self._cb_cam.addItem("Нет устройств")
        else:
            for idx, label in found:
                self._cb_cam.addItem(label, idx)
        self._cb_cam.setEnabled(True)
        self._btn_open.setEnabled(True)

    def _open_camera(self):
        if _cv2 is None:
            self._lbl_status.setText("opencv-python не установлен")
            return
        idx = self._cb_cam.currentData()
        if idx is None:
            return
        if self._cap:
            self._cap.release()
        self._cap = _cv2.VideoCapture(idx, _cv2.CAP_DSHOW)
        self._cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
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

    title = QLabel("Параметры оборудования стенда")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ecf0f1; background: transparent; border: none;")
    title.setWordWrap(True)
    lay.addWidget(title)

    sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setStyleSheet("QFrame { color: #4a6278; }")
    lay.addWidget(sep1)

    from PyQt6.QtWidgets import QFormLayout
    form = QFormLayout()
    form.setSpacing(6)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    try:
        import json as _json
        with open("params.json", "r", encoding="utf-8") as _f:
            _si = _json.load(_f).get("stand_info", {})
    except (FileNotFoundError, ValueError):
        _si = {}

    fields = [
        ("Марка и модель стенда:",  _si.get("stand_model", "")),
        ("Серийный номер стенда:",  _si.get("stand_serial", "")),
        ("Дата аттестации стенда:", _si.get("stand_date", "")),
        ("Марка и модель СИ 1:",    _si.get("si1_model", "")),
        ("Марка и модель СИ 2:",    _si.get("si2_model", "")),
    ]
    for label, value in fields:
        le = QLabel(value)
        form.addRow(label, le)
    lay.addLayout(form)

    sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("QFrame { color: #4a6278; }")
    lay.addWidget(sep2)

    btn_alarm_test = QPushButton("Тест аварии")
    btn_alarm_test.setStyleSheet("""
        QPushButton {
            background: #7b241c; color: #ecf0f1;
            border: 1px solid #e74c3c; border-radius: 3px;
            padding: 4px 8px; font-size: 11px;
        }
        QPushButton:hover   { background: #e74c3c; }
        QPushButton:pressed { background: #c0392b; }
    """)

    def _emit_alarm():
        from gui.windows.experiment_window.ui_experiment_wiget import ExperimentWidget
        w = btn_alarm_test.parent()
        while w is not None:
            if isinstance(w, ExperimentWidget):
                w.alarm_test.emit()
                return
            w = w.parent()

    btn_alarm_test.clicked.connect(_emit_alarm)

    ctrl_title = QLabel("Управление")
    ctrl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1abc9c; background: transparent; border: none;")
    lay.addWidget(ctrl_title)

    _toggle_style = """
        QPushButton {{
            background: {off}; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 4px;
            padding: 4px 10px; font-size: 11px; min-height: 24px;
        }}
        QPushButton:checked {{
            background: #1abc9c; border-color: #1abc9c; color: #1a252f;
        }}
        QPushButton:hover {{ background: #4a6a82; }}
    """

    btn_power = QPushButton("Включить привод")
    btn_power.setCheckable(True)
    btn_power.setStyleSheet(_toggle_style.format(off="#3d5166"))

    btn_manual = QPushButton("Ручной режим")
    btn_manual.setCheckable(True)
    btn_manual.setStyleSheet(_toggle_style.format(off="#3d5166"))

    _arrow_style = """
        QPushButton {
            font-size: 22px; background: #3d5166; color: #ecf0f1;
            border: 1px solid #4a6278; border-radius: 6px;
        }
        QPushButton:hover   { background: #4a6a82; }
        QPushButton:pressed { background: #2980b9; }
    """

    btn_up = QPushButton("▲")
    btn_up.setFixedSize(48, 48)
    btn_up.setStyleSheet(_arrow_style)

    btn_down = QPushButton("▼")
    btn_down.setFixedSize(48, 48)
    btn_down.setStyleSheet(_arrow_style)

    # Скорость + тоглы + сброс/авария на одной строке
    motion_row = QHBoxLayout()
    motion_row.setSpacing(8)

    arrows_col = QVBoxLayout()
    arrows_col.setSpacing(4)
    arrows_col.addWidget(btn_up)
    arrows_col.addWidget(btn_down)

    speed_col = QVBoxLayout()
    speed_col.setSpacing(2)
    speed_lbl = QLabel("Скорость мм/сек: 0.01")
    speed_lbl.setStyleSheet("font-size: 11px; color: #7f8c8d; background: transparent; border: none;")
    speed_col.addWidget(speed_lbl)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 600)
    slider.setValue(1)
    slider.setFixedWidth(120)
    slider.valueChanged.connect(lambda v: speed_lbl.setText(f"Скорость мм/сек: {v / 100:.2f}"))
    speed_col.addWidget(slider)

    right_col = QVBoxLayout()
    right_col.setSpacing(4)
    right_col.addWidget(btn_power)
    right_col.addWidget(btn_manual)

    extra_row = QHBoxLayout()
    extra_row.setSpacing(6)
    extra_row.addWidget(btn_alarm_test)
    extra_row.addWidget(QPushButton("Сброс"))
    extra_row.addStretch()

    motion_row.addLayout(arrows_col)
    motion_row.addLayout(speed_col)
    motion_row.addLayout(right_col)
    lay.addLayout(motion_row)
    lay.addLayout(extra_row)

    sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
    sep3.setStyleSheet("QFrame { color: #4a6278; }")
    lay.addWidget(sep3)

    # Текущая позиция
    lbl_pos = QLabel("Текущая позиция: 0")
    pos_row = QHBoxLayout()
    pos_row.addWidget(lbl_pos)
    pos_row.addStretch()
    pos_row.addWidget(QPushButton("Обнулить L"))
    lay.addLayout(pos_row)

    # Нагрузка
    lbl_load = QLabel("Нагрузка, Н: 0")
    load_row = QHBoxLayout()
    load_row.addWidget(lbl_load)
    load_row.addStretch()
    load_row.addWidget(QPushButton("Обнулить Н"))
    load_row.addStretch()
    lbl_dh = QLabel("Скорость нагружения H, сек: 0")
    load_row.addWidget(lbl_dh)
    lay.addLayout(load_row)

    sep_cam = QFrame(); sep_cam.setFrameShape(QFrame.Shape.HLine)
    sep_cam.setStyleSheet("QFrame { color: #4a6278; background: #4a6278; }")
    lay.addWidget(sep_cam)
    lay.addWidget(_CameraWidget(), 1)

    lay.addStretch()
    scroll.setWidget(container)
    return scroll
