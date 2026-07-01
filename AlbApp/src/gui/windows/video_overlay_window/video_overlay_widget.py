"""Вкладка «График на видео»: врезает график трендов в записанные ролики.

Выбираешь записи rec_*.avi (рядом должен лежать сайдкар rec_*.csv с временем
кадров), настраиваешь оверлей и получаешь рядом файлы rec_*_chart.avi.
"""
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QListWidget, QListWidgetItem, QSpinBox, QSlider, QComboBox, QCheckBox,
    QProgressBar, QFileDialog, QGroupBox, QSplitter,
)
from PyQt6.QtCore import Qt

from ._overlay_worker import CHANNELS
from ._video_player import VideoPlayer

CHANNEL_NAMES = [c[2] for c in CHANNELS]


class VideoOverlayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._worker = None
        self._setup_ui()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ── шапка ─────────────────────────────────────────────────────────────
        title = QLabel("Видеоналожение")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        root.addWidget(title)

        hint = QLabel(
            "Врезает график трендов в записанные ролики. Рядом с rec_*.avi нужен "
            "сайдкар rec_*.csv (создаётся при записи). Результат — rec_*_chart.avi."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa5b1;")
        root.addWidget(hint)

        # ── главная область: слева управление, справа плеер ───────────────────
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_controls())

        self._player = VideoPlayer()
        split.addWidget(self._player)
        split.setStretchFactor(0, 0)     # колонка управления — фикс
        split.setStretchFactor(1, 1)     # плеер тянется
        split.setSizes([430, 1200])
        root.addWidget(split, 1)

        self._refresh_run_enabled()

    def _build_controls(self) -> QWidget:
        """Левая колонка: файлы, параметры, запуск, прогресс."""
        col = QWidget()
        col.setMaximumWidth(480)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # выбор файлов
        files_row = QHBoxLayout()
        self._btn_pick = QPushButton("Выбрать записи…")
        self._btn_pick.clicked.connect(self._pick_files)
        self._btn_clear = QPushButton("Очистить")
        self._btn_clear.clicked.connect(self._clear_files)
        files_row.addWidget(self._btn_pick)
        files_row.addWidget(self._btn_clear)
        files_row.addStretch()
        v.addLayout(files_row)

        self._list = QListWidget()
        self._list.setMinimumHeight(90)
        self._list.setToolTip("Двойной клик — открыть файл в плеере")
        self._list.itemDoubleClicked.connect(self._on_item_dblclick)
        v.addWidget(self._list, 1)

        # параметры оверлея — компактная вертикальная форма
        opts = QGroupBox("Параметры оверлея")
        og = QVBoxLayout(opts)
        og.setSpacing(6)

        self._sp_window = QSpinBox(); self._sp_window.setRange(5, 3600); self._sp_window.setValue(300)
        self._sp_window.setFixedWidth(90)
        og.addLayout(self._field_row("Окно графика, сек:", self._sp_window))

        self._sp_size = QSpinBox(); self._sp_size.setRange(15, 90); self._sp_size.setValue(33)
        self._sp_size.setFixedWidth(90)
        og.addLayout(self._field_row("Размер, % ширины:", self._sp_size))

        self._cb_pos = QComboBox()
        self._cb_pos.addItem("Правый нижний",  "br")
        self._cb_pos.addItem("Левый нижний",   "bl")
        self._cb_pos.addItem("Правый верхний", "tr")
        self._cb_pos.addItem("Левый верхний",  "tl")
        og.addLayout(self._field_row("Положение:", self._cb_pos))

        self._sl_opacity = QSlider(Qt.Orientation.Horizontal)
        self._sl_opacity.setRange(0, 100); self._sl_opacity.setValue(60)
        self._lbl_opacity = QLabel("60%"); self._lbl_opacity.setFixedWidth(40)
        self._sl_opacity.valueChanged.connect(lambda val: self._lbl_opacity.setText(f"{val}%"))
        op_row = self._field_row("Прозрачность фона:", self._sl_opacity, stretch_field=True)
        op_row.addWidget(self._lbl_opacity)
        og.addLayout(op_row)

        og.addWidget(QLabel("Каналы:"))
        self._ch_checks = []
        for name in CHANNEL_NAMES:
            cb = QCheckBox(name); cb.setChecked(True)
            self._ch_checks.append(cb)
            og.addWidget(cb)

        self._cb_demo = QCheckBox("Демо-данные (синтетика вместо Influx)")
        self._cb_demo.setToolTip("Рисовать график из синтетических данных, без обращения к базе")
        self._cb_demo.toggled.connect(self._refresh_run_enabled)
        og.addWidget(self._cb_demo)

        v.addWidget(opts)

        # запуск
        run_row = QHBoxLayout()
        self._btn_run = QPushButton("Создать видео с графиком")
        self._btn_run.setStyleSheet(
            "QPushButton { background: #1abc9c; color: #10141a; font-weight: bold;"
            " border-radius: 4px; padding: 8px 18px; }"
            "QPushButton:hover { background: #16a085; }"
            "QPushButton:disabled { background: #4a6278; color: #9aa5b1; }"
        )
        self._btn_run.clicked.connect(self._start)
        self._btn_cancel = QPushButton("Отмена")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._cancel)
        run_row.addWidget(self._btn_run, 1)
        run_row.addWidget(self._btn_cancel)
        v.addLayout(run_row)

        self._progress = QProgressBar(); self._progress.setValue(0)
        v.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #9aa5b1;")
        v.addWidget(self._status)

        return col

    @staticmethod
    def _field_row(label: str, field, stretch_field: bool = False) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel(label); lbl.setFixedWidth(150)
        row.addWidget(lbl)
        row.addWidget(field, 1 if stretch_field else 0)
        if not stretch_field:
            row.addStretch()
        return row

    # ── файлы ─────────────────────────────────────────────────────────────────

    def _initial_dir(self) -> str:
        try:
            from gui.windows.settings_window.tab_wigets.ui_cameras_settings import load_camera_settings
            d = load_camera_settings().get("save_dir")
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
        return os.path.expanduser("~")

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать записи", self._initial_dir(),
            "Видео (*.avi *.mp4 *.mkv);;Все файлы (*)")
        for f in files:
            if f not in self._files:
                self._files.append(f)
        self._rebuild_list()

    def _clear_files(self):
        self._files.clear()
        self._rebuild_list()

    def _rebuild_list(self):
        self._list.clear()
        for f in self._files:
            sidecar = os.path.splitext(f)[0] + ".csv"
            ok = os.path.exists(sidecar)
            mark = "✓ сайдкар" if ok else "✗ нет сайдкара"
            item = QListWidgetItem(f"{os.path.basename(f)}    [{mark}]")
            if not ok:
                item.setForeground(Qt.GlobalColor.gray)
            self._list.addItem(item)
        self._refresh_run_enabled()

    def _on_item_dblclick(self, item):
        row = self._list.row(item)
        if 0 <= row < len(self._files):
            self._player.open(self._files[row])

    def _refresh_run_enabled(self):
        running = self._worker is not None and self._worker.isRunning()
        if self._cb_demo.isChecked():
            ok = len(self._files) > 0          # в демо сайдкар не нужен
        else:
            ok = any(os.path.exists(os.path.splitext(f)[0] + ".csv") for f in self._files)
        self._btn_run.setEnabled(ok and not running)

    # ── запуск обработки ───────────────────────────────────────────────────────

    def _start(self):
        from ._overlay_worker import OverlayWorker, _render_label_bgra

        channels = [cb.isChecked() for cb in self._ch_checks]

        # Подписи каналов (кириллица) рисуем здесь, в GUI-потоке: QPainter вне
        # GUI-потока на Windows может зависнуть. В воркер уходят готовые битмапы.
        base_px = 40
        labels_hires = []
        for i, (meas, field, name, color, step) in enumerate(CHANNELS):
            if not channels[i]:
                labels_hires.append(None)
                continue
            rgb = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
            labels_hires.append(_render_label_bgra(name, rgb, base_px))

        opts = {
            "window_secs":   self._sp_window.value(),
            "size_pct":      self._sp_size.value(),
            "opacity":       self._sl_opacity.value(),
            "position":      self._cb_pos.currentData(),
            "channels":      channels,
            "demo":          self._cb_demo.isChecked(),
            "labels_hires":  labels_hires,
            "label_base_px": base_px,
        }
        self._worker = OverlayWorker(list(self._files), opts, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._set_running(True)
        self._worker.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.abort()
            self._status.setText("Отмена…")

    def _set_running(self, running: bool):
        self._btn_cancel.setEnabled(running)
        self._btn_pick.setEnabled(not running)
        self._btn_clear.setEnabled(not running)
        if running:
            self._btn_run.setEnabled(False)
        else:
            self._refresh_run_enabled()

    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._status.setText(msg)

    def _on_file_done(self, path: str):
        self._status.setText(f"Готово: {os.path.basename(path)}")

    def _on_finished(self, files: list):
        self._set_running(False)
        self._progress.setValue(100 if files else 0)
        if files:
            self._status.setText(f"Готово файлов: {len(files)}. "
                                 f"Сохранены рядом с исходниками (*_chart.avi).")
            self._player.open(files[0])      # сразу показать первый результат
        else:
            self._status.setText("Ничего не обработано (нет валидных записей с сайдкаром).")
        self._worker = None

    def _on_failed(self, err: str):
        self._set_running(False)
        self._status.setText(f"Ошибка: {err}")
        self._worker = None

    # ── тема (вызывается из MainWindow.apply_theme) ────────────────────────────

    def set_theme(self, dark: bool):
        pass
