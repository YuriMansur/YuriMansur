"""Лёгкий встроенный видеоплеер на OpenCV.

QtMultimedia на XVID/.avi капризен к кодекам, а OpenCV в этом проекте и так
читает такие файлы — поэтому крутим кадры через cv2 + QTimer в GUI-потоке
(для превью 720p этого с запасом хватает).

Панель управления (play/pause + ползунок перемотки + время) лежит поверх
кадра и всплывает только при наведении курсора. Видимость определяем опросом
позиции курсора по таймеру — как оверлей камеры в section1: enter/leave на
родителе мерцают, когда курсор уходит на дочерние кнопки.
"""
import cv2
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSlider
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QCursor


_CONTROLS_QSS = """
QWidget#playerControls { background: rgba(0,0,0,150); border-radius: 6px; }
QWidget#playerControls QLabel { color: white; background: transparent; font-size: 12px; }
QPushButton#playPause {
    background: transparent; color: white; border: none; font-size: 16px;
}
QPushButton#playPause:hover { color: #1abc9c; }
QSlider::groove:horizontal { background: rgba(255,255,255,70); height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #1abc9c; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal {
    background: white; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
}
"""


class VideoPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap = None
        self._fps = 25.0
        self._total = 0
        self._frame = None          # последний декодированный кадр (BGR) для масштабирования
        self._playing = False
        self._seeking = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumSize(320, 180)

        # экран — на всю площадь виджета (геометрия выставляется в resizeEvent)
        self._screen = QLabel("Видео не выбрано", self)
        self._screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen.setStyleSheet("background: #111; color: #777; border: 1px solid #333;")

        # всплывающая панель управления поверх кадра
        self._controls = QWidget(self)
        self._controls.setObjectName("playerControls")
        self._controls.setStyleSheet(_CONTROLS_QSS)
        cl = QHBoxLayout(self._controls)
        cl.setContentsMargins(10, 4, 12, 4)
        cl.setSpacing(8)

        self._btn_play = QPushButton("▶", self._controls)
        self._btn_play.setObjectName("playPause")
        self._btn_play.setFixedWidth(28)
        self._btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.clicked.connect(self.toggle)
        self._btn_play.setEnabled(False)
        cl.addWidget(self._btn_play)

        self._slider = QSlider(Qt.Orientation.Horizontal, self._controls)
        self._slider.setEnabled(False)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._slider.valueChanged.connect(self._on_slider_value)
        cl.addWidget(self._slider, 1)

        self._lbl_time = QLabel("00:00 / 00:00", self._controls)
        self._lbl_time.setMinimumWidth(92)
        self._lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self._lbl_time)

        self._controls.hide()

        # таймер опроса наведения для показа/скрытия панели
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(120)
        self._hover_timer.timeout.connect(self._update_controls)
        self._hover_timer.start()

    # ── управление ───────────────────────────────────────────────────────────

    def open(self, path: str, autoplay: bool = True):
        self._release()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            self._screen.setText("Не удалось открыть видео")
            return False
        self._cap = cap
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        self._total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        self._slider.blockSignals(True)
        self._slider.setRange(0, max(self._total - 1, 0))
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._slider.setEnabled(True)
        self._btn_play.setEnabled(True)
        self._read_and_show(0)
        if autoplay:
            self.play()
        else:
            self._update_time(0)
        return True

    def play(self):
        if self._cap is None:
            return
        # с конца — начинаем сначала
        if self._slider.value() >= self._total - 1:
            self._seek(0)
        self._playing = True
        self._btn_play.setText("⏸")
        self._timer.start(int(1000 / max(self._fps, 1)))

    def pause(self):
        self._playing = False
        self._btn_play.setText("▶")
        self._timer.stop()

    def toggle(self):
        self.pause() if self._playing else self.play()

    # ── всплывающая панель ─────────────────────────────────────────────────────

    def _update_controls(self):
        pos = self.mapFromGlobal(QCursor.pos())
        hovered = self.rect().contains(pos) and self._cap is not None
        if hovered and not self._controls.isVisible():
            self._position_controls()
            self._controls.show()
            self._controls.raise_()
        elif not hovered and self._controls.isVisible():
            self._controls.hide()

    def _position_controls(self):
        m, h = 12, 36
        self._controls.setGeometry(m, self.height() - h - m, self.width() - 2 * m, h)

    # ── внутреннее ─────────────────────────────────────────────────────────────

    def _next_frame(self):
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok:
            self.pause()
            return
        self._frame = frame
        self._show(frame)
        pos = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        self._slider.blockSignals(True)
        self._slider.setValue(min(pos, self._slider.maximum()))
        self._slider.blockSignals(False)
        self._update_time(pos)

    def _read_and_show(self, frame_idx: int):
        if self._cap is None:
            return
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = self._cap.read()
        if ok:
            self._frame = frame
            self._show(frame)
        self._update_time(frame_idx)

    def _seek(self, frame_idx: int):
        self._slider.blockSignals(True)
        self._slider.setValue(frame_idx)
        self._slider.blockSignals(False)
        self._read_and_show(frame_idx)

    def _on_slider_pressed(self):
        self._seeking = True

    def _on_slider_released(self):
        self._seeking = False
        self._read_and_show(self._slider.value())

    def _on_slider_value(self, value: int):
        # реагируем только на ручное перетаскивание (программные апдейты с blockSignals)
        if self._seeking:
            self._read_and_show(value)

    def _show(self, frame):
        h, w = frame.shape[:2]
        img = QImage(frame.data, w, h, w * 3, QImage.Format.Format_BGR888)
        pix = QPixmap.fromImage(img).scaled(
            self._screen.width(), self._screen.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._screen.setPixmap(pix)

    def _update_time(self, frame_idx: int):
        cur = frame_idx / max(self._fps, 1)
        tot = self._total / max(self._fps, 1)
        self._lbl_time.setText(f"{self._fmt(cur)} / {self._fmt(tot)}")

    @staticmethod
    def _fmt(sec: float) -> str:
        sec = int(sec)
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._screen.setGeometry(self.rect())
        if self._controls.isVisible():
            self._position_controls()
        if self._frame is not None:
            self._show(self._frame)

    def _release(self):
        self._timer.stop()
        self._playing = False
        self._btn_play.setText("▶")
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def closeEvent(self, event):
        self._hover_timer.stop()
        self._release()
        super().closeEvent(event)
