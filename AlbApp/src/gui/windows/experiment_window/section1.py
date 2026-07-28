import datetime, os, time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSlider,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap

from event_bus import bus   # статусы привода (cmd_status) для подсветки кнопок

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None



import threading as _threading





class _FrameWorker(QThread):
    frame_ready = pyqtSignal('PyQt_PyObject')
    fps_updated = pyqtSignal(int)

    def __init__(self, cap):
        super().__init__()
        self._cap  = cap
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import time
        last_frame = 0.0
        fps_count  = 0
        fps_ts     = time.monotonic()

        while not self._stop:
            self._cap.grab()
            ok, frame = self._cap.retrieve()
            if ok and frame is not None:
                self.frame_ready.emit(frame)
                fps_count += 1

            now = time.monotonic()
            if now - fps_ts >= 1.0:
                self.fps_updated.emit(fps_count)
                fps_count = 0
                fps_ts    = now

            sleep = max(0, 0.033 - (now - last_frame))
            last_frame = now
            if sleep:
                self.msleep(int(sleep * 1000))

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


class _SilentProber(QThread):
    """Запрашивает возможности камеры через DirectShow без захвата кадров."""
    done  = pyqtSignal(int, list, list)  # cam_idx, resolutions, fps_list
    _lock = _threading.Lock()

    def __init__(self, cam_idx: int, device_idx: int):
        super().__init__()
        self._cam_idx    = cam_idx
        self._device_idx = device_idx

    def run(self):
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._run_probe()
        finally:
            self._lock.release()

    def _run_probe(self):
        try:
            from pygrabber.dshow_graph import FilterGraph
            graph = FilterGraph()
            graph.add_video_input_device(self._device_idx)
            formats = graph.get_input_device().get_formats()

            seen_res, seen_fps = set(), set()
            supported_res, supported_fps = [], []

            for fmt in formats:
                w, h = fmt.get('width', 0), fmt.get('height', 0)
                fps  = fmt.get('fps', 0)
                if w and h:
                    key = (w, h)
                    if key not in seen_res:
                        seen_res.add(key)
                        supported_res.append(f"{w}x{h}")
                if fps:
                    f = round(fps)
                    if f not in seen_fps:
                        seen_fps.add(f)
                        supported_fps.append(f)

            supported_res.sort(key=lambda s: int(s.split('x')[0]))
            supported_fps.sort()

        except Exception:
            supported_res, supported_fps = [], []

        if not supported_res:
            supported_res = ["1280x720"]
        if not supported_fps:
            supported_fps = [30]

        self.done.emit(self._cam_idx, supported_res, supported_fps)


class _CameraWidget(QWidget):
    recording_changed  = pyqtSignal(bool)        # True — запись началась, False — остановлена
    cameras_found      = pyqtSignal(list)         # список (idx, name)
    capabilities_found = pyqtSignal(list, list)   # supported_resolutions, supported_fps

    def __init__(self, cam_idx: int = 0, parent=None):
        super().__init__(parent)
        self._cam_idx   = cam_idx
        self._cap       = None
        self._writer    = None
        self._ts_file   = None   # сайдкар: реальное время каждого записанного кадра
        self._recording = False
        self._found: list = []   # последний результат скана: [(device_idx, name), ...]
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

        self._btn_open = QPushButton("▶")
        self._btn_rec  = QPushButton("⏺")
        self._btn_stop = QPushButton("⏹")
        self._lbl_status = QLabel("Камера закрыта")
        self._btn_rec.setEnabled(False)
        self._btn_stop.setEnabled(False)
        for btn in (self._btn_open, self._btn_rec, self._btn_stop):
            btn.setFixedSize(28, 28)

        ov_lay = QHBoxLayout(self._overlay)
        ov_lay.setContentsMargins(6, 4, 6, 4)
        ov_lay.setSpacing(4)
        ov_lay.addWidget(self._btn_open)
        ov_lay.addWidget(self._btn_rec)
        ov_lay.addWidget(self._btn_stop)
        self._overlay.adjustSize()

        # имя камеры — отдельный виджет внизу слева
        self._lbl_cam_name = QLabel(self._get_cam_name(), self)
        self._lbl_cam_name.setStyleSheet(
            "QLabel { color: white; font-size: 11px; font-weight: bold;"
            " background: rgba(0,0,0,150); border-radius: 3px; padding: 2px 7px; }"
        )
        self._lbl_cam_name.adjustSize()
        self._lbl_cam_name.hide()

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

    def _get_cam_name(self) -> str:
        import json
        key = "cam1" if self._cam_idx == 0 else "cam2"
        dev_id, fallback = None, ""
        try:
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "camera_settings.json")
            with open(os.path.normpath(cfg_path), "r", encoding="utf-8") as f:
                slot = json.load(f).get(key, {})
            dev_id   = slot.get("device_id")
            fallback = slot.get("device_name", "")
        except Exception:
            pass

        # Предпочитаем живое имя из последнего скана по device_id, а не
        # сохранённую (возможно устаревшую) строку. Одинаковые камеры
        # различаем по порядковому номеру среди тёзок.
        if dev_id is not None:
            same_name = [n for i, n in self._found if i == dev_id]
            if same_name:
                name  = same_name[0]
                dupes = [i for i, n in self._found if n == name]
                if len(dupes) > 1:
                    name = f"{name} #{dupes.index(dev_id) + 1}"
                return name
            # скан уже прошёл, а настроенного устройства нет — не показываем
            # устаревшее имя из конфига
            if self._found:
                return f"Камера {self._cam_idx + 1}"

        return fallback or f"Камера {self._cam_idx + 1}"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._preview.setGeometry(self.rect())
        self._overlay.adjustSize()
        margin = 8
        self._overlay.move(self.width() - self._overlay.width() - margin, margin)
        self._rec_indicator.adjustSize()
        self._rec_indicator.move(margin, margin)
        self._lbl_cam_name.adjustSize()
        self._lbl_cam_name.move(margin, self.height() - self._lbl_cam_name.height() - margin)

    def _update_overlay(self):
        from PyQt6.QtGui import QCursor
        pos = self.mapFromGlobal(QCursor.pos())
        hovered = self.rect().contains(pos)
        if hovered and not self._overlay.isVisible():
            self._overlay.show()
            self._overlay.raise_()
            self._lbl_cam_name.show()
            self._lbl_cam_name.raise_()
        elif not hovered and self._overlay.isVisible():
            self._overlay.hide()
            self._lbl_cam_name.hide()

    def _do_scan(self):
        self._scanner = _CamScanner()
        self._scanner.done.connect(self._on_cameras_found)
        self._scanner.start()

    def _on_cameras_found(self, found: list):
        self._found = found
        self.cameras_found.emit(found)
        self._btn_open.setEnabled(bool(found))
        # обновляем название если камера не открыта
        if not (self._cap and self._cap.isOpened()):
            self._lbl_cam_name.setText(self._get_cam_name())
            self._lbl_cam_name.adjustSize()
            margin = 8
            self._lbl_cam_name.move(margin, self.height() - self._lbl_cam_name.height() - margin)

        if not found or (self._cap and self._cap.isOpened()):
            return
        if getattr(self, '_silent_prober', None) and self._silent_prober.isRunning():
            return

        from gui.windows.settings_window.tab_wigets.ui_cameras_settings import load_camera_settings
        cfg = load_camera_settings()

        # device_ids уже сохранённых в конфиге камер
        configured_ids = {
            c.get("device_id")
            for c in (cfg.get("cam1", {}), cfg.get("cam2", {}))
            if c.get("device_id") is not None
        }

        # для текущего виджета — если есть конфиг с resolution+fps, отдаём сразу
        key = "cam1" if self._cam_idx == 0 else "cam2"
        saved = cfg.get(key, {})
        if saved.get("resolution") and saved.get("fps"):
            self.capabilities_found.emit([saved["resolution"]], [saved["fps"]])
            return

        # ищем первую камеру из найденных, которой ещё нет в конфиге
        to_probe = [idx for idx, _ in found if idx not in configured_ids]
        if not to_probe:
            return

        self._silent_prober = _SilentProber(0, to_probe[0])
        self._silent_prober.done.connect(
            lambda _, res, fps: self.capabilities_found.emit(res, fps)
        )
        self._silent_prober.start()

    def _open_camera(self):
        if _cv2 is None:
            self._lbl_status.setText("opencv-python не установлен")
            return
        if self._cap and self._cap.isOpened():
            self._close_camera()
            return
        from gui.windows.settings_window.tab_wigets.ui_cameras_settings import load_camera_settings
        s = load_camera_settings()
        key = "cam1" if self._cam_idx == 0 else "cam2"
        idx = s.get(key, {}).get("device_id")
        if idx is None:
            self._lbl_status.setText("Камера не выбрана в настройках")
            return

        self._lbl_cam_name.setText(self._get_cam_name())
        self._overlay.adjustSize()

        self._cap = _cv2.VideoCapture(idx, _cv2.CAP_DSHOW)
        self._cap.set(_cv2.CAP_PROP_FRAME_WIDTH,  9999)
        self._cap.set(_cv2.CAP_PROP_FRAME_HEIGHT, 9999)
        self._cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
        if self._cap.isOpened():
            self._btn_open.setText("⏹")
            self._lbl_status.setText("Камера открыта")
            self._start_worker()
        else:
            self._cap = None
            self._lbl_status.setText(f"Камера {idx} недоступна")



    def _on_capabilities(self, resolutions: list, fps_list: list):
        self.capabilities_found.emit(resolutions, fps_list)

    def _start_worker(self):
        if self._cap and self._cap.isOpened():
            w = int(self._cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
            name = self._get_cam_name()
            self._cam_info = f"{name}  {w}×{h}"
            self._lbl_cam_name.setText(self._cam_info)
            self._lbl_cam_name.adjustSize()
            margin = 8
            self._lbl_cam_name.move(margin, self.height() - self._lbl_cam_name.height() - margin)

            self._worker = _FrameWorker(self._cap)
            self._worker.frame_ready.connect(self._on_frame)
            self._worker.fps_updated.connect(self._on_fps)
            self._worker.start()
            self._btn_rec.setEnabled(True)
            self._btn_stop.setEnabled(True)
            self._lbl_status.setText("Камера открыта")

    def _start_record(self):
        if not self._cap or not self._cap.isOpened():
            return
        w = int(self._cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.expanduser("~"), f"rec_{ts}.avi")
        fourcc = _cv2.VideoWriter_fourcc(*"XVID")
        self._writer = _cv2.VideoWriter(path, fourcc, 25.0, (w, h))

        # Сайдкар: на каждый записанный кадр — его реальное UTC-время (unix, сек).
        # Нужен вкладке наложения графика для точной синхронизации видео с InfluxDB:
        # writer жёстко на 25 fps, а реальный темп захвата плавает.
        try:
            self._ts_file = open(os.path.splitext(path)[0] + ".csv", "w",
                                 encoding="utf-8", buffering=1)
            self._ts_file.write("frame,timestamp\n")
            self._frame_no = 0
        except OSError:
            self._ts_file = None

        self._recording = True
        self.recording_changed.emit(True)
        self._btn_rec.setEnabled(False)
        self._lbl_status.setText(f"● Запись → {os.path.basename(path)}")
        self._rec_indicator.show()
        self._rec_indicator.raise_()
        self._rec_blink.start()

    def _stop(self):
        self._recording = False
        self.recording_changed.emit(False)
        self._rec_blink.stop()
        self._rec_indicator.hide()
        if self._writer:
            self._writer.release()
            self._writer = None
        if self._ts_file is not None:
            self._ts_file.close()
            self._ts_file = None
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
        self._lbl_cam_name.setText(self._get_cam_name())
        self._lbl_cam_name.adjustSize()

    def _on_fps(self, fps: int):
        self._lbl_cam_name.setText(
            f"{self._cam_info}  {fps}fps"
        )
        self._lbl_cam_name.adjustSize()

    def _on_frame(self, frame):
        if self._recording and self._writer:
            self._writer.write(frame)
            if self._ts_file is not None:
                # время кадра пишем в том же порядке, в каком кадры идут в файл
                self._ts_file.write(f"{self._frame_no},{time.time():.6f}\n")
                self._frame_no += 1
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


_STATUS_ACTIVE_STYLE = ("border: 2px solid #2ecc71; border-radius: 4px;"
                        " background: rgba(46,204,113,0.25);")


class _DriveStatusBinder(QObject):
    """Подсветка кнопок привода по cmd_status с ПЛК.

    Воркер раскладывает массив cmd_status по enum s_names и шлёт статусы как
    tag_state с именем '<prefix><s_name>' (блок 'status' в servers.json). Здесь
    сопоставляем имя статуса → кнопка и подсвечиваем активную. Живёт как child
    контейнера секции — при пересборке UI Qt сам отключает слот от шины."""

    def __init__(self, mapping: dict, prefix: str = "st:", parent=None):
        super().__init__(parent)
        # ключ шины (имя с префиксом) → (кнопка, её базовый стиль)
        self._map = {prefix + name: (btn, btn.styleSheet()) for name, btn in mapping.items()}
        bus.tag_state.connect(self._on_status)

    def _on_status(self, name: str, val):
        entry = self._map.get(name)
        if entry is None:
            return
        btn, base = entry
        btn.setStyleSheet(base + _STATUS_ACTIVE_STYLE if val else base)


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
    ctrl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1abc9c;")
    lay.addWidget(ctrl_title)

    btn_power_on  = QPushButton("Вкл. привод")
    btn_power_off = QPushButton("Выкл. привод")

    # Режим управления — текстовая индикация (значение обновляется извне)
    lbl_mode = QLabel("Ручной")
    lbl_mode.setObjectName("modeLabel")
    lbl_mode.setStyleSheet(
        "QLabel#modeLabel { font-family: 'Segoe UI Semibold', 'Segoe UI', sans-serif;"
        " font-size: 15px; font-weight: bold; color: #1abc9c; background: transparent; }")
    lbl_mode.setAlignment(Qt.AlignmentFlag.AlignHCenter)   # значение по центру подписи
    container._mode_label = lbl_mode   # ссылка для обновления режима

    btn_up = QPushButton("▲")
    btn_up.setFixedSize(42, 42)

    btn_down = QPushButton("▼")
    btn_down.setFixedSize(42, 42)

    # запись команд в PLC (commands[...] через cmd-очередь):
    # Вкл./Выкл. привод — две кнопки (EN_DRIVER / DIS_DRIVER),
    # ▲/▼ — толчок (TRUE пока нажато, FALSE при отпускании)
    from tag_binder import tags
    btn_power_on .clicked.connect(lambda: tags.write("cmdEnableDriver", 1))
    btn_power_off.clicked.connect(lambda: tags.write("cmdDisableDriver", 1))
    btn_up.pressed.connect(lambda: tags.write("cmdBackwardJog", 1))
    btn_up.released.connect(lambda: tags.write("cmdBackwardJog", 0))
    btn_down.pressed.connect(lambda: tags.write("cmdForwardJog", 1))
    btn_down.released.connect(lambda: tags.write("cmdForwardJog", 0))

    # Подсветка кнопок по фактическому статусу привода с ПЛК (cmd_status → st:<имя>).
    # Имена — члены s_names на ПЛК (см. лог воркера "[worker] статусы:").
    container._drive_status = _DriveStatusBinder({
        "BW_JOGGING":      btn_up,         # ▲ = толчок назад (backward)
        "FW_JOGGING":      btn_down,       # ▼ = толчок вперёд (forward)
    }, prefix="st:", parent=container)

    # Каждая группа — в своём виджете-обёртке; в строке выравниваем по центру
    # по вертикали, чтобы колонки разной высоты не «уезжали».

    # режим управления: подпись + значение
    mode_col = QVBoxLayout(); mode_col.setContentsMargins(0, 0, 0, 0); mode_col.setSpacing(3)
    mode_cap = QLabel("Режим управления")
    mode_cap.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")
    mode_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)   # подпись по центру, как значение
    mode_col.addWidget(mode_cap)
    mode_col.addWidget(lbl_mode)
    mode_w = QWidget(); mode_w.setLayout(mode_col)

    # вкл/выкл привод — одна над другой, равной ширины
    btn_power_on.setMinimumWidth(120)
    btn_power_off.setMinimumWidth(120)
    power_col = QVBoxLayout(); power_col.setContentsMargins(0, 0, 0, 0); power_col.setSpacing(6)
    power_col.addWidget(btn_power_on)
    power_col.addWidget(btn_power_off)
    power_w = QWidget(); power_w.setLayout(power_col)

    # скорость: подпись + слайдер
    speed_col = QVBoxLayout(); speed_col.setContentsMargins(0, 0, 0, 0); speed_col.setSpacing(4)
    speed_lbl = QLabel("Скорость: 0.01 мм/с")
    speed_lbl.setStyleSheet("background: transparent;")
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 600); slider.setValue(1); slider.setMinimumWidth(40)
    slider.valueChanged.connect(lambda v: speed_lbl.setText(f"Скорость: {v / 100:.2f} мм/с"))
    speed_col.addWidget(speed_lbl)
    speed_col.addWidget(slider)
    speed_w = QWidget(); speed_w.setLayout(speed_col)

    # стрелки-толчки ▲/▼ рядом
    arrows_row = QHBoxLayout(); arrows_row.setContentsMargins(0, 0, 0, 0); arrows_row.setSpacing(6)
    arrows_row.addWidget(btn_up)
    arrows_row.addWidget(btn_down)
    arrows_w = QWidget(); arrows_w.setLayout(arrows_row)

    # порядок слева направо: режим · вкл/выкл · скорость · стрелки.
    # speed_w тянется (stretch=1) и забирает свободную ширину — остальные фиксированы,
    # поэтому стрелки всегда видны справа, а при узкой панели ужимается слайдер.
    _vc = Qt.AlignmentFlag.AlignVCenter
    motion_row = QHBoxLayout()
    motion_row.setSpacing(12)
    motion_row.addWidget(mode_w,   0, _vc)
    motion_row.addWidget(power_w,  0, _vc)
    motion_row.addWidget(speed_w,  1, _vc)
    motion_row.addWidget(arrows_w, 0, _vc)
    lay.addLayout(motion_row)

    sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
    lay.addWidget(sep3)

    # Текущая позиция
    lbl_pos = QLabel("Текущая позиция: 0")
    pos_row = QHBoxLayout()
    pos_row.addWidget(lbl_pos)
    pos_row.addStretch()
    btn_zero_l = QPushButton("Обнулить L")
    pos_row.addWidget(btn_zero_l)
    lay.addLayout(pos_row)

    # Нагрузка
    lbl_load = QLabel("Нагрузка, Н: 0")
    load_row = QHBoxLayout()
    load_row.addWidget(lbl_load)
    load_row.addStretch()
    btn_zero_h = QPushButton("Обнулить Н")
    load_row.addWidget(btn_zero_h)
    load_row.addStretch()
    lbl_dh = QLabel("Скорость нагружения H, сек: 0")
    load_row.addWidget(lbl_dh)
    lay.addLayout(load_row)

    # Ручное управление стендом. На время идущего испытания блокируется: приводом
    # распоряжается методика (секция 3), а обнуление датчиков посреди испытания
    # исказило бы показания. Переключает set_manual_controls_enabled().
    container._manual_controls = [btn_power_on, btn_power_off, slider,
                                  btn_up, btn_down, btn_zero_l, btn_zero_h]

    sep_cam = QFrame(); sep_cam.setFrameShape(QFrame.Shape.HLine)
    lay.addWidget(sep_cam)

    from PyQt6.QtWidgets import QSizePolicy
    cam1 = _CameraWidget(cam_idx=0)
    cam1.setMinimumHeight(180)
    cam1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(cam1, 1)

    cam2 = _CameraWidget(cam_idx=1)
    cam2.setMinimumHeight(180)
    cam2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(cam2, 1)
    scroll.setWidget(container)
    return scroll, btn_alarm_test


def set_manual_controls_enabled(section1: QWidget, enabled: bool) -> None:
    """Разблокировать/заблокировать ручное управление стендом (панель «Управление»).

    section1 — то, что вернул _make_section1(): QScrollArea с контейнером внутри.
    """
    inner = section1.widget() if isinstance(section1, QScrollArea) else section1
    for w in getattr(inner, "_manual_controls", []):
        w.setEnabled(enabled)
