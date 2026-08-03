import datetime, os, time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSlider, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QEvent, QSize
from PyQt6.QtGui import QPixmap, QIcon, QColor, QFont
from PyQt6.QtWidgets import QToolTip

from event_bus import bus   # статусы привода (cmd_status) для подсветки кнопок
from gui.icons import make_icon
from tag_binder import tags, link   # значения тегов ПЛК + состояние связи

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None



import threading as _threading





class _RecSession:
    """Общая сессия записи камер: одна метка времени и один сайдкар на обе.

    Ролики пишутся в разные файлы — `rec_<стамп>_cam1.avi` и `..._cam2.avi`,
    иначе вторая камера, стартовавшая в ту же секунду, затирала бы первую.
    Таблица «кадр → время» при этом одна: наложение графика берёт время по
    номеру кадра, а камеры пишутся через один writer на 25 fps и стартуют
    вместе, поэтому вторая таблица повторяла бы первую.

    Ведёт её камера, начавшая запись первой; вторая только присоединяется.
    Файл закрывается, когда запись остановили обе.
    """

    _stamp: str = ""
    _file = None
    _users: int = 0
    _frame_no: int = 0

    @classmethod
    def join(cls) -> tuple[str, bool]:
        """Войти в сессию. Возвращает (метка времени, вести ли сайдкар)."""
        owner = cls._users == 0
        if owner:
            cls._stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            cls._frame_no = 0
            try:
                path = os.path.join(os.path.expanduser("~"), f"rec_{cls._stamp}.csv")
                cls._file = open(path, "w", encoding="utf-8", buffering=1)
                cls._file.write("frame,timestamp\n")
            except OSError:
                cls._file = None
        cls._users += 1
        return cls._stamp, owner

    @classmethod
    def write_frame_time(cls, ts: float) -> None:
        if cls._file is not None:
            cls._file.write(f"{cls._frame_no},{ts:.6f}\n")
            cls._frame_no += 1

    @classmethod
    def leave(cls) -> None:
        cls._users = max(0, cls._users - 1)
        if cls._users == 0 and cls._file is not None:
            cls._file.close()
            cls._file = None


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

    # Все созданные камеры панели: запись идёт на всех сразу, а не на той, чью
    # кнопку нажали, — ролик испытания должен быть с обеих точек съёмки.
    _instances: list = []

    def __init__(self, cam_idx: int = 0, parent=None):
        super().__init__(parent)
        self._cam_idx   = cam_idx
        self._cap       = None
        self._writer    = None
        self._ts_owner  = False  # эта камера ведёт общий сайдкар (см. _RecSession)
        self._recording = False
        _CameraWidget._instances.append(self)
        self._found: list = []   # последний результат скана: [(device_idx, name), ...]
        self._worker: _FrameWorker | None = None
        self.setMouseTracking(True)

        # превью на весь виджет
        self._preview = QLabel("Нет сигнала")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setParent(self)
        self._preview.setGeometry(self.rect())
        self._preview.setMouseTracking(True)


        # индикатор записи (левый верхний угол): красный мигающий «REC» —
        # символ-точка перед ним зависел от шрифта, а смысла не добавлял
        self._rec_indicator = QLabel("REC", self)
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

        # значки рисуются кодом (gui/icons.py) — символы юникода в разных темах
        # и шрифтах выглядели по-разному
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        from gui.icons import make_icon
        self._btn_open = QPushButton()
        self._btn_rec  = QPushButton()
        self._btn_stop = QPushButton()
        for btn, kind, tip in ((self._btn_open, "eye",     "Открыть камеру"),
                               (self._btn_rec,  "record",  "Начать запись"),
                               (self._btn_stop, "stop_sq", "Остановить запись")):
            btn.setIcon(QIcon(make_icon(kind, "#ffffff", 14)))
            btn.setIconSize(QSize(14, 14))
            btn.setToolTip(tip)
        self._lbl_status = QLabel("Камера закрыта")
        self._btn_rec.setEnabled(False)
        self._btn_stop.setEnabled(False)
        for btn in (self._btn_open, self._btn_rec, self._btn_stop):
            btn.setFixedSize(28, 28)
        self._set_open_icon(opened=False)

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
        # через lambda: clicked передаёт checked первым аргументом, а там _peer
        self._btn_rec.clicked.connect(lambda: self._start_record())
        self._btn_stop.clicked.connect(lambda: self._stop())

        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(5000)
        self._scan_timer.timeout.connect(self._do_scan)
        self._scan_timer.start()
        self._do_scan()

    def _set_open_icon(self, opened: bool):
        """Кнопка открытия камеры: «открыть» ⇄ «закрыть».

        Меняем именно значок и подсказку — раньше поверх иконки дописывался
        текстовый символ, и на кнопке оказывалось два обозначения сразу.
        """
        from PyQt6.QtGui import QIcon
        from gui.icons import make_icon
        kind, tip = ("eye_off", "Закрыть камеру") if opened else ("eye", "Открыть камеру")
        self._btn_open.setIcon(QIcon(make_icon(kind, "#ffffff", 14)))
        self._btn_open.setToolTip(tip)

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
            # кнопка становится «закрыть» — меняем значок, а не подписываем текстом
            # поверх него (иначе рядом с иконкой торчал старый символ)
            self._set_open_icon(opened=True)
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

    def _peers(self) -> list:
        """Остальные живые камеры панели — запись идёт и снимается на всех.

        Пересобранные виджеты остаются в списке мёртвыми обёртками (панель
        перестраивается, например, при смене темы), поэтому отсеиваем их здесь.
        """
        alive = []
        for cam in list(_CameraWidget._instances):
            if cam is self:
                continue
            try:
                cam.isVisible()          # у удалённого виджета бросит RuntimeError
            except RuntimeError:
                _CameraWidget._instances.remove(cam)
                continue
            alive.append(cam)
        return alive

    def _start_record(self, _peer: bool = False):
        if self._recording:
            return
        if not self._cap or not self._cap.isOpened():
            if not _peer:
                # нажали запись, а вторая камера закрыта — сказать об этом
                self._lbl_status.setText("Камера не открыта — запись не начата")
            return
        w = int(self._cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        # Номер камеры в имени обязателен: без него две камеры, начавшие запись
        # в одну секунду, писали бы в один файл. Сайдкар — общий (см. _RecSession).
        stamp, self._ts_owner = _RecSession.join()
        path = os.path.join(os.path.expanduser("~"),
                            f"rec_{stamp}_cam{self._cam_idx + 1}.avi")
        fourcc = _cv2.VideoWriter_fourcc(*"XVID")
        self._writer = _cv2.VideoWriter(path, fourcc, 25.0, (w, h))

        self._recording = True
        self.recording_changed.emit(True)
        self._btn_rec.setEnabled(False)
        self._lbl_status.setText(f"Запись → {os.path.basename(path)}")
        self._rec_indicator.show()
        self._rec_indicator.raise_()
        self._rec_blink.start()

        if not _peer:                     # подхватить остальные камеры
            idle = []
            for cam in self._peers():
                cam._start_record(_peer=True)
                if not cam._recording:
                    idle.append(str(cam._cam_idx + 1))
            if idle:
                # ролик выйдет только с одной точки — оператор должен это видеть
                self._lbl_status.setText(
                    f"Запись → {os.path.basename(path)}"
                    f"  (камера {', '.join(idle)} закрыта — без записи)")

    def _stop(self, _peer: bool = False):
        was_recording = self._recording
        self._recording = False
        self.recording_changed.emit(False)
        self._rec_blink.stop()
        self._rec_indicator.hide()
        if self._writer:
            self._writer.release()
            self._writer = None
        if was_recording:
            # сайдкар закроется, когда запись остановят обе камеры
            _RecSession.leave()
            self._ts_owner = False
        self._btn_rec.setEnabled(True)
        self._lbl_status.setText("Камера открыта")

        if was_recording and not _peer:   # остановить остальные камеры
            for cam in self._peers():
                cam._stop(_peer=True)

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
        self._set_open_icon(opened=False)
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
            if self._ts_owner:
                # время кадра пишем в том же порядке, в каком кадры идут в файл
                _RecSession.write_frame_time(time.time())
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

    # значки кнопок рисуются кодом — см. gui/icons.py
    from PyQt6.QtGui import QIcon
    from PyQt6.QtCore import QSize
    from gui.icons import make_icon

    def _with_icon(btn: QPushButton, kind: str, px: int = 18) -> QPushButton:
        btn.setIcon(QIcon(make_icon(kind, "#e6e6e6", px)))
        btn.setIconSize(QSize(px, px))
        return btn

    # только значок, надпись — во всплывающей подсказке
    btn_power_on  = _with_icon(QPushButton(), "power_on",  20)
    btn_power_off = _with_icon(QPushButton(), "power_off", 20)
    btn_power_on.setToolTip("Вкл. привод")
    btn_power_off.setToolTip("Выкл. привод")

    # Режим управления — такая же карточка, как у показаний и состояния
    # (значение обновляется извне через container._mode_label.setText)
    mode_card = _Readout("Режим управления", "", _RO_MODE, sample="Автоматический")
    mode_card.setText("Ручной")
    container._mode_label = mode_card

    btn_up = _with_icon(QPushButton(), "arrow_up", 20)
    btn_up.setFixedSize(42, 42)
    btn_up.setToolTip("Толчок назад")

    btn_down = _with_icon(QPushButton(), "arrow_down", 20)
    btn_down.setFixedSize(42, 42)
    btn_down.setToolTip("Толчок вперёд")

    # запись команд в PLC (commands[...] через cmd-очередь):
    # Вкл./Выкл. привод — две кнопки (EN_DRIVER / DIS_DRIVER),
    # ▲/▼ — толчок (TRUE пока нажато, FALSE при отпускании)
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

    # вкл/выкл привод — одна над другой, равной ширины
    # без надписи кнопки квадратные — как толчки ▲/▼ рядом
    btn_power_on.setFixedSize(42, 42)
    btn_power_off.setFixedSize(42, 42)
    power_col = QHBoxLayout(); power_col.setContentsMargins(0, 0, 0, 0); power_col.setSpacing(6)
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

    # Режим и состояние — одной строкой над органами управления: обе карточки
    # про то, в каком стенд сейчас положении, а не про управление им.
    # Ширину делят поровну, как и ряд показаний ниже (см. vals_row).
    container._state_card = state_card = _StateCard()
    mode_row = QHBoxLayout(); mode_row.setSpacing(6)
    for card in (mode_card, state_card):
        card.setMinimumWidth(card.sizeHint().width())
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        mode_row.addWidget(card, 1)
    lay.addLayout(mode_row)

    # порядок слева направо: вкл/выкл · скорость · стрелки.
    # speed_w тянется (stretch=1) и забирает свободную ширину — остальные фиксированы,
    # поэтому стрелки всегда видны справа, а при узкой панели ужимается слайдер.
    _vc = Qt.AlignmentFlag.AlignVCenter
    motion_row = QHBoxLayout()
    motion_row.setSpacing(12)
    motion_row.addWidget(power_w,  0, _vc)
    motion_row.addWidget(speed_w,  1, _vc)
    motion_row.addWidget(arrows_w, 0, _vc)
    lay.addLayout(motion_row)

    sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
    lay.addWidget(sep3)

    # Показания стенда: позиция, нагрузка, скорость нагружения. Каждое — своя
    # карточка со своим цветом, чтобы оператор находил нужное число не читая
    # подписи. Кнопки обнуления живут внутри своих карточек.
    btn_zero_l = QPushButton(" L"); btn_zero_l.setToolTip("Обнулить положение")
    btn_zero_h = QPushButton(" Н"); btn_zero_h.setToolTip("Обнулить нагрузку")
    for b in (btn_zero_l, btn_zero_h):
        b.setFixedSize(40, 26)      # квадратнее: сплюснутые выглядели зажатыми

    # sample — самое широкое значение, какое сюда попадёт: под него отводится
    # место, чтобы карточка не прыгала при смене числа и не занимала лишнего.
    ro_pos   = _Readout("Позиция", "мм",  _RO_POS,  btn_zero_l, "1000.00")
    ro_load  = _Readout("Нагрузка",        "Н",   _RO_LOAD, btn_zero_h, "5000.0")
    # подпись короткая: «Н/с» уже говорит, что это скорость нагружения, а
    # длинное слово растягивало карточку и ряд не влезал в ширину панели
    ro_speed = _Readout("Скорость", "Н/с", _RO_SPEED, sample="999.0")
    ro_speed.setText("0")

    # Три показания в один ряд: нагрузка, позиция, скорость нагружения.
    # Свободную ширину делят поровну, а не оставляют пустоту справа. Минимум —
    # собственный размер карточки: ужиматься и обрезать подписи им нельзя,
    # на узком окне ряд лучше выйдет за край с прокруткой.
    vals_row = QHBoxLayout(); vals_row.setSpacing(6)
    for card in (ro_load, ro_pos, ro_speed):
        card.setMinimumWidth(card.sizeHint().width())
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        vals_row.addWidget(card, 1)
    lay.addLayout(vals_row)

    # Ручное управление стендом. На время идущего испытания блокируется: приводом
    # распоряжается методика (секция 3), а обнуление датчиков посреди испытания
    # исказило бы показания. Переключает set_manual_controls_enabled().
    # Позиция и нагрузка — живые значения с ПЛК, те же потоки, что у окошек
    # секции 4: displacement (мм) и tenza (Н).
    container._live_values = _LiveValues({
        "displacement": (ro_pos,  "{}", 2),
        "tenza":        (ro_load, "{}", 1),
    }, parent=container)

    # подсказки кнопок без надписей должны работать и когда панель заблокирована
    container._tip_relay = _ToolTipRelay(container)
    container.installEventFilter(container._tip_relay)

    container._manual_controls = [btn_power_on, btn_power_off, slider,
                                  btn_up, btn_down, btn_zero_l, btn_zero_h]

    sep_cam = QFrame(); sep_cam.setFrameShape(QFrame.Shape.HLine)
    lay.addWidget(sep_cam)

    cam1 = _CameraWidget(cam_idx=0)
    cam1.setMinimumHeight(180)
    cam1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(cam1, 1)

    cam2 = _CameraWidget(cam_idx=1)
    cam2.setMinimumHeight(180)
    cam2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(cam2, 1)
    scroll.setWidget(container)
    return scroll


# Цвета показаний. Разные у каждого, чтобы число опознавалось по цвету, а не по
# подписи; те же оттенки, что у навигации и статусов стенда.
_RO_POS   = "#3498db"    # положение — синий
_RO_LOAD  = "#e67e22"    # нагрузка — оранжевый
_RO_SPEED = "#1abc9c"    # скорость нагружения — бирюзовый
_RO_MODE  = "#9b59b6"    # режим управления — фиолетовый


class _Readout(QFrame):
    """Показание стенда: подпись, крупное цветное значение, единица измерения.

    Фон и рамка — сам цвет показания, разведённый до полупрозрачного, поэтому
    карточка одинаково читается и на светлой, и на тёмной теме: она подмешивается
    к тому фону, который под ней, а не задаёт свой.

    Кнопка (обнуление) необязательна и уезжает вправо; её значок перекрашивается
    в цвет карточки — белый на светлой теме терялся бы.
    """

    def __init__(self, caption: str, unit: str, color: str,
                 button: QPushButton = None, sample: str = "1000.00"):
        super().__init__()
        self.setObjectName("readout")
        self._btn = button
        # шире содержимого не растём: карточки стоят слева, а не делят панель
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        cap = QLabel(caption.upper())
        cap.setStyleSheet("color: #7f8c8d; font-size: 10px; font-weight: 600;")

        self._val = QLabel("—")
        # Размер шрифта — через QFont, а не stylesheet: иначе fontMetrics() ниже
        # мерил бы обычным шрифтом и место под значение вышло бы вдвое меньше.
        f = self._val.font(); f.setPixelSize(18); f.setWeight(QFont.Weight.DemiBold)
        self._val.setFont(f)
        # место под самое широкое значение: единица не ездит вслед за числом
        self._val.setFixedWidth(self._val.fontMetrics().horizontalAdvance(sample) + 2)
        val_row = QHBoxLayout(); val_row.setContentsMargins(0, 0, 0, 0)
        val_row.setSpacing(4)
        val_row.addWidget(self._val, 0, Qt.AlignmentFlag.AlignBottom)
        if unit:
            # единица прижата к низу значения — на общей с ним базовой линии
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px;")
            val_row.addWidget(unit_lbl, 0, Qt.AlignmentFlag.AlignBottom)
        val_row.addStretch()

        col = QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(1)
        col.addWidget(cap)
        col.addLayout(val_row)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 6, 5)
        row.setSpacing(7)
        row.addLayout(col, 1)
        if button is not None:
            button.setIconSize(QSize(17, 17))
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.set_accent(color)

    def set_accent(self, color: str):
        """Перекрасить карточку целиком: рамку, фон, значение и значок кнопки."""
        self.setStyleSheet(
            f"#readout {{ background: {_rgba(color, 30)};"
            f" border: 1px solid {_rgba(color, 90)};"
            f" border-left: 3px solid {color};"
            f" border-radius: 6px; }}"
            " #readout QLabel { background: transparent; }"
        )
        self._val.setStyleSheet(f"color: {color};")   # размер задан шрифтом
        if self._btn is not None:
            self._btn.setIcon(QIcon(make_icon("zero", color, 18)))

    def setText(self, text: str):
        """Показать значение (совместимо с QLabel — так его правит _LiveValues)."""
        self._val.setText(text)


class _StateCard(_Readout):
    """Состояние стенда одним словом: Готовность · Работа · Авария.

    Считается по фактическим состояниям, а не по цвету индикаторов: авария —
    st:GENERAL_FAULT, работа — идущее испытание либо движущийся привод
    (st:FW_JOGGING / st:BW_JOGGING), готовность — питание и исправные датчики
    без аварии.

    Когда ни одно не выполняется (нет связи, снято питание, отказали датчики),
    слова нет: показываем прочерк, а причину — подсказкой. Врать «Готовность»
    при неготовом стенде нельзя, а четвёртого слова в списке не задано.
    """

    _READY = "#2ecc71"
    _RUN   = "#3498db"
    _FAULT = "#e74c3c"
    _NONE  = "#7f8c8d"

    def __init__(self):
        # место под самое длинное слово, иначе карточка меняла бы ширину
        super().__init__("Состояние", "", self._NONE, sample="Готовность")
        self._running = False
        bus.tag_state.connect(self._on_tag)
        link.changed.connect(lambda *_: self._refresh())
        self._refresh()

    def set_test_running(self, running: bool):
        """Испытание идёт (секция 3 запустила методику)."""
        self._running = running
        self._refresh()

    _WATCHED = ("st:GENERAL_FAULT", "st:DRIVE_POWER", "st:SENSORS_GOOD",
                "st:FW_JOGGING", "st:BW_JOGGING")

    def _on_tag(self, name: str, _value):
        if name in self._WATCHED:
            self._refresh()

    def _refresh(self):
        word, color, tip = self._state()
        self.setText(word)
        self.set_accent(color)
        self.setToolTip(tip)

    def _state(self):
        if link.state != link.UP:
            return "—", self._NONE, "Нет связи с ПЛК: состояние неизвестно"
        if tags.last("st:GENERAL_FAULT"):
            return "Авария", self._FAULT, "Авария на стенде"
        if self._running or tags.last("st:FW_JOGGING") or tags.last("st:BW_JOGGING"):
            return "Работа", self._RUN, "Идёт нагружение"
        if not tags.last("st:DRIVE_POWER"):
            return "—", self._NONE, "Привод обесточен"
        if not tags.last("st:SENSORS_GOOD"):
            return "—", self._NONE, "Датчики неисправны"
        return "Готовность", self._READY, "Стенд готов к нагружению"


def _rgba(hex_color: str, alpha: int) -> str:
    """Цвет темы, разведённый до полупрозрачного (alpha 0…255)."""
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


class _LiveValues(QObject):
    """Живые значения датчиков в карточках «Позиция» и «Нагрузка».

    Источник тот же, что у окошек секции 4 — поток bus.stream_points (имена
    потоков заданы в servers.json, logging.ring → points_msg). Из батча берём
    последнее значение, а метки обновляем по таймеру: батчи приходят ~10 раз в
    секунду, чаще перерисовывать текст незачем.
    """

    REFRESH_MS = 200

    def __init__(self, labels: dict, parent=None):
        # labels: имя потока → (метка, шаблон, точность)
        super().__init__(parent)
        self._labels = labels
        self._last: dict = {}
        bus.stream_points.connect(self._on_points)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.REFRESH_MS)

    def _on_points(self, name: str, _times: list, vals: list):
        if vals and name in self._labels:
            self._last[name] = vals[-1]

    def _refresh(self):
        for name, (lbl, tpl, prec) in self._labels.items():
            val = self._last.get(name)
            lbl.setText(tpl.format("—" if val is None else f"{float(val):.{prec}f}"))


class _ToolTipRelay(QObject):
    """Показывает подсказку дочерней кнопки, даже когда та заблокирована.

    Qt не показывает подсказки неактивных виджетов и адресует событие родителю.
    На время испытания панель управления блокируется, а подсказки у кнопок без
    надписей — единственное объяснение, что они делают, поэтому рисуем сами.
    """

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.ToolTip:
            child = obj.childAt(ev.pos())
            if child is not None and child.toolTip():
                QToolTip.showText(ev.globalPos(), child.toolTip(), obj)
                return True
        return False


def set_manual_controls_enabled(section1: QWidget, enabled: bool) -> None:
    """Разблокировать/заблокировать ручное управление стендом (панель «Управление»).

    section1 — то, что вернул _make_section1(): QScrollArea с контейнером внутри.
    """
    inner = section1.widget() if isinstance(section1, QScrollArea) else section1
    for w in getattr(inner, "_manual_controls", []):
        w.setEnabled(enabled)


def set_test_running(section1: QWidget, running: bool) -> None:
    """Сообщить панели, что идёт испытание — карточка состояния покажет «Работа»."""
    inner = section1.widget() if isinstance(section1, QScrollArea) else section1
    card = getattr(inner, "_state_card", None)
    if card is not None:
        card.set_test_running(running)
