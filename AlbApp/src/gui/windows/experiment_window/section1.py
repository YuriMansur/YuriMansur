import datetime, os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSlider,
    QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None



import threading as _threading

class _FrameWorker(QThread):
    """Захватывает кадры в фоне, шлёт сигнал в GUI-поток."""
    frame_ready = pyqtSignal(object)  # numpy array

    def __init__(self, cap):
        super().__init__()
        self._cap  = cap
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        while not self._stop:
            self._cap.grab()          # сбрасываем буфер без декодирования
            ok, frame = self._cap.retrieve()
            if ok and frame is not None:
                self.frame_ready.emit(frame)
            self.msleep(16)           # ~60 fps max

class _CamComboBox(QComboBox):
    def showPopup(self):
        from PyQt6.QtCore import QPoint
        super().showPopup()
        view = self.view()
        if view and view.window():
            w = view.window()
            pos = self.mapToGlobal(QPoint(0, self.height()))
            w.move(pos)

class _CamScanner(QThread):
    done = pyqtSignal(list)
    _lock = _threading.Lock()

    def run(self):
        if not self._lock.acquire(blocking=False):
            return  # другой виджет уже сканирует
        try:
            from pygrabber.dshow_graph import FilterGraph
            names = FilterGraph().get_input_devices()
        except Exception:
            names = []
        finally:
            self._lock.release()
        self.done.emit(list(enumerate(names)))


class _CameraWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap       = None
        self._writer    = None
        self._recording = False
        self._worker: _FrameWorker | None = None
        self.setMouseTracking(True)

        # превью на весь виджет
        self._preview = QLabel("Нет сигнала")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setParent(self)
        self._preview.setGeometry(self.rect())
        self._preview.setMouseTracking(True)

        # индикатор записи (левый верхний угол)
        self._rec_indicator = QLabel("⏺ REC", self)
        self._rec_indicator.setStyleSheet("""
            QLabel {
                color: #ff3b3b; font-size: 12px; font-weight: bold;
                background: rgba(0,0,0,160); border-radius: 4px;
                padding: 2px 8px;
            }
        """)
        self._rec_indicator.hide()
        self._rec_blink = QTimer(self)
        self._rec_blink.setInterval(600)
        self._rec_blink.timeout.connect(
            lambda: self._rec_indicator.setVisible(not self._rec_indicator.isVisible())
        )

        # накладная панель управления (правый верхний угол)
        self._overlay = QWidget(self)
        self._overlay.hide()

        self._cb_cam   = _CamComboBox()
        self._cb_cam.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._btn_open    = QPushButton("▶")
        self._btn_rec     = QPushButton("⏺")
        self._btn_stop    = QPushButton("⏹")
        self._btn_refresh = None
        self._lbl_status  = QLabel("Камера закрыта")
        self._btn_rec.setEnabled(False)
        self._btn_stop.setEnabled(False)
        for btn in (self._btn_open, self._btn_rec, self._btn_stop):
            btn.setFixedSize(28, 28)

        ov_lay = QHBoxLayout(self._overlay)
        ov_lay.setContentsMargins(6, 4, 6, 4)
        ov_lay.setSpacing(4)
        ov_lay.addWidget(self._cb_cam)
        ov_lay.addWidget(self._btn_open)
        ov_lay.addWidget(self._btn_rec)
        ov_lay.addWidget(self._btn_stop)
        self._overlay.adjustSize()

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(100)
        self._hover_timer.timeout.connect(self._update_overlay)
        self._hover_timer.start()

        self._btn_open.clicked.connect(self._open_camera)
        self._btn_rec.clicked.connect(self._start_record)
        self._btn_stop.clicked.connect(self._stop)

        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(5000)
        self._scan_timer.timeout.connect(self._do_scan)
        self._scan_timer.start()
        self._do_scan()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._preview.setGeometry(self.rect())
        self._overlay.adjustSize()
        margin = 8
        self._overlay.move(self.width() - self._overlay.width() - margin, margin)
        self._rec_indicator.adjustSize()
        self._rec_indicator.move(margin, margin)

    def _update_overlay(self):
        from PyQt6.QtGui import QCursor
        pos = self.mapFromGlobal(QCursor.pos())
        hovered = self.rect().contains(pos) or self._cb_cam.view().isVisible()
        if hovered and not self._overlay.isVisible():
            self._overlay.show()
            self._overlay.raise_()
        elif not hovered and self._overlay.isVisible():
            self._overlay.hide()

    def _do_scan(self):
        self._scanner = _CamScanner()
        self._scanner.done.connect(self._on_cameras_found)
        self._scanner.start()

    def _on_cameras_found(self, found: list):

        # обновляем комбобокс только если список изменился
        current_labels = [self._cb_cam.itemText(i) for i in range(self._cb_cam.count())]
        new_labels = [label for _, label in found]
        if current_labels == new_labels:
            return

        prev = self._cb_cam.currentData()
        self._cb_cam.blockSignals(True)
        self._cb_cam.clear()
        if not found:
            self._cb_cam.addItem("Нет устройств")
        else:
            for idx, label in found:
                self._cb_cam.addItem(label, idx)
            for i in range(self._cb_cam.count()):
                if self._cb_cam.itemData(i) == prev:
                    self._cb_cam.setCurrentIndex(i)
                    break
        self._cb_cam.blockSignals(False)
        self._cb_cam.setEnabled(True)
        self._btn_open.setEnabled(bool(found))
        # зафиксировать ширину по самому длинному пункту
        fm = self._cb_cam.fontMetrics()
        max_w = max((fm.horizontalAdvance(self._cb_cam.itemText(i))
                     for i in range(self._cb_cam.count())), default=100)
        self._cb_cam.setMinimumWidth(max_w + 52)  # +52 на стрелку, отступы и запас
        self._overlay.adjustSize()
        margin = 8
        self._overlay.move(self.width() - self._overlay.width() - margin, margin)

    def _open_camera(self):
        if _cv2 is None:
            self._lbl_status.setText("opencv-python не установлен")
            return
        if self._cap and self._cap.isOpened():
            self._close_camera()
            return
        idx = self._cb_cam.currentData()
        if idx is None:
            return
        self._cap = _cv2.VideoCapture(idx, _cv2.CAP_DSHOW)
        self._cap.set(_cv2.CAP_PROP_FRAME_WIDTH, 9999)
        self._cap.set(_cv2.CAP_PROP_FRAME_HEIGHT, 9999)
        self._cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
        if self._cap.isOpened():
            self._worker = _FrameWorker(self._cap)
            self._worker.frame_ready.connect(self._on_frame)
            self._worker.start()
            self._btn_rec.setEnabled(True)
            self._btn_stop.setEnabled(True)
            self._btn_open.setText("⏹")
            self._lbl_status.setText("Камера открыта")
        else:
            self._cap = None
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
        self._lbl_status.setText(f"● Запись → {os.path.basename(path)}")
        self._rec_indicator.show()
        self._rec_indicator.raise_()
        self._rec_blink.start()

    def _stop(self):
        self._recording = False
        self._rec_blink.stop()
        self._rec_indicator.hide()
        if self._writer:
            self._writer.release()
            self._writer = None
        self._btn_rec.setEnabled(True)
        self._lbl_status.setText("Камера открыта")

    def _close_camera(self):
        self._stop()
        if self._worker:
            self._worker.frame_ready.disconnect(self._on_frame)
            self._worker.stop()
            self._worker.wait()
            self._worker = None
        if self._cap:
            self._cap.release()
            self._cap = None
        self._preview.setPixmap(QPixmap())
        self._preview.setText("Нет сигнала")
        self._btn_open.setText("▶")
        self._btn_rec.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._lbl_status.setText("Камера закрыта")

    def _on_frame(self, frame):
        if self._recording and self._writer:
            self._writer.write(frame)
        try:
            from PyQt6.QtGui import QImage
            from PyQt6.QtCore import QRect
            h, w = frame.shape[:2]
            img = QImage(frame.data, w, h, w * 3, QImage.Format.Format_BGR888)
            pw = self._preview.width() or w
            ph = self._preview.height() or h
            pix = QPixmap.fromImage(img).scaled(
                pw, ph,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            if pix.width() > pw or pix.height() > ph:
                x = (pix.width() - pw) // 2
                y = (pix.height() - ph) // 2
                pix = pix.copy(QRect(x, y, pw, ph))
            self._preview.setPixmap(pix)
        except Exception:
            pass

    def closeEvent(self, event):
        self._scan_timer.stop()
        self._hover_timer.stop()
        self._close_camera()
        super().closeEvent(event)


def _make_section1() -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    container = QWidget()
    lay = QVBoxLayout(container)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.setSpacing(8)

    btn_alarm_test = QPushButton("Тест аварии")

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
    lay.addWidget(ctrl_title)

    btn_power = QPushButton("Вкл. привод")
    btn_power.setCheckable(True)

    btn_manual = QPushButton("Ручной режим")
    btn_manual.setCheckable(True)

    btn_up = QPushButton("▲")
    btn_up.setFixedSize(48, 48)

    btn_down = QPushButton("▼")
    btn_down.setFixedSize(48, 48)

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
    speed_col.addWidget(speed_lbl)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 600)
    slider.setValue(1)
    slider.setFixedWidth(120)
    slider.valueChanged.connect(lambda v: speed_lbl.setText(f"Скорость мм/сек: {v / 100:.2f}"))
    speed_col.addWidget(slider)

    btn_reset = QPushButton("Сброс")

    def _emit_reset():
        from gui.windows.experiment_window.ui_experiment_wiget import ExperimentWidget
        w = btn_reset.parent()
        while w is not None:
            if isinstance(w, ExperimentWidget):
                w.alarm_reset.emit()
                return
            w = w.parent()

    btn_reset.clicked.connect(_emit_reset)

    right_col = QVBoxLayout()
    right_col.setSpacing(4)
    toggle_row = QHBoxLayout()
    toggle_row.setSpacing(4)
    toggle_row.addWidget(btn_power)
    toggle_row.addWidget(btn_manual)
    right_col.addLayout(toggle_row)
    alarm_row = QHBoxLayout()
    alarm_row.setSpacing(4)
    alarm_row.addWidget(btn_alarm_test)
    alarm_row.addWidget(btn_reset)
    right_col.addLayout(alarm_row)

    motion_row.addLayout(arrows_col)
    motion_row.addLayout(speed_col)
    motion_row.addLayout(right_col)
    lay.addLayout(motion_row)

    sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
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
    lay.addWidget(sep_cam)

    from PyQt6.QtWidgets import QSizePolicy
    cam1 = _CameraWidget()
    cam1.setMinimumHeight(180)
    cam1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(cam1, 1)

    cam2 = _CameraWidget()
    cam2.setMinimumHeight(180)
    cam2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(cam2, 1)
    scroll.setWidget(container)
    return scroll
