from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QLineEdit, QFileDialog, QFormLayout,
    QLabel, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import json, os

_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "camera_settings.json")
_SETTINGS_FILE = os.path.normpath(_SETTINGS_FILE)


def load_camera_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save(data: dict):
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class _ProbeWorker(QThread):
    """Сканирует возможности камеры через pygrabber и сохраняет в конфиг."""
    done = pyqtSignal(int, str, list, list)  # device_idx, device_name, resolutions, fps_list

    def __init__(self, device_idx: int, device_name: str):
        super().__init__()
        self._device_idx  = device_idx
        self._device_name = device_name

    _FPS_TO_TRY = [5, 10, 15, 20, 24, 25, 30, 60, 90, 120]

    _COMMON_FPS = [5, 10, 15, 20, 24, 25, 30, 60, 90, 120]

    def run(self):
        res_fps_map: dict[str, list] = {}
        try:
            import re, subprocess, imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            result = subprocess.run(
                [ffmpeg, '-f', 'dshow', '-list_options', 'true',
                 '-i', f'video={self._device_name}'],
                capture_output=True, text=True, timeout=10
            )
            # парсим строки вида: min s=1920x1080 fps=5 max s=1920x1080 fps=30
            pattern = re.compile(
                r'min s=(\d+x\d+) fps=([\d.]+) max s=\1 fps=([\d.]+)'
            )
            res_fps_raw: dict[str, tuple] = {}  # res -> (min_fps, max_fps)
            for line in result.stderr.splitlines():
                m = pattern.search(line)
                if m:
                    res, fps_min, fps_max = m.group(1), float(m.group(2)), float(m.group(3))
                    cur = res_fps_raw.get(res, (fps_min, fps_max))
                    res_fps_raw[res] = (min(cur[0], fps_min), max(cur[1], fps_max))

            for res, (fps_min, fps_max) in sorted(
                res_fps_raw.items(), key=lambda kv: int(kv[0].split('x')[0])
            ):
                fps_list = [f for f in self._COMMON_FPS if fps_min <= f <= fps_max]
                if fps_list:
                    res_fps_map[res] = fps_list
        except Exception:
            pass

        if not res_fps_map:
            res_fps_map = {"1280x720": [30]}

        cfg = load_camera_settings()
        cfg.setdefault("devices", {})[str(self._device_idx)] = {
            "name":        self._device_name,
            "res_fps_map": res_fps_map,
        }
        _save(cfg)

        resolutions = list(res_fps_map.keys())
        self.done.emit(self._device_idx, self._device_name, resolutions, [])


class CameraSettingsWidget(QWidget):
    settings_saved = pyqtSignal()  # эмитится после сохранения

    def __init__(self, parent=None):
        super().__init__(parent)
        self._found: list = []
        self._available_ids: set = set()
        self._probe_worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        lbl_cameras = QLabel("Камеры")
        lbl_cameras.setStyleSheet("font-size: 15px; font-weight: bold; color: #9b59b6;")
        root.addWidget(lbl_cameras)

        saved = load_camera_settings()

        # ── Главный горизонтальный ряд ────────────────────────────────────────
        from PyQt6.QtWidgets import QGridLayout
        main_row = QGridLayout()
        main_row.setSpacing(16)
        main_row.setColumnStretch(0, 1)
        main_row.setColumnStretch(1, 1)

        # ── Фрейм: Доступные устройства ───────────────────────────────────────
        dev_frame = QFrame()
        dev_frame.setObjectName("camSection")
        dev_frame.setStyleSheet("QFrame#camSection { border: 1px solid #555555; border-radius: 4px; }")
        dev_frame_lay = QVBoxLayout(dev_frame)
        dev_frame_lay.setContentsMargins(8, 8, 8, 8)
        dev_frame_lay.setSpacing(8)

        lbl_dev = QLabel("Доступные устройства")
        lbl_dev.setStyleSheet("font-size: 13px; font-weight: bold;")
        dev_frame_lay.addWidget(lbl_dev)

        self._cb_devices = QComboBox()
        self._cb_devices.addItem("Сканирование...", userData=None)
        self._cb_devices.currentIndexChanged.connect(self._on_device_selected)
        dev_frame_lay.addWidget(self._cb_devices)

        self._lbl_probe = QLabel("")
        self._lbl_probe.setStyleSheet("color: gray; font-size: 11px;")
        dev_frame_lay.addWidget(self._lbl_probe)

        self._btn_add = QPushButton("Добавить")
        self._btn_add.setEnabled(False)
        self._btn_add.setStyleSheet(
            "QPushButton { background: #2980b9; color: white; font-weight: bold;"
            " border-radius: 4px; min-height: 30px; }"
            "QPushButton:hover { background: #3498db; }"
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        self._btn_add.clicked.connect(self._add_to_config)
        dev_frame_lay.addWidget(self._btn_add)

        # ── Фрейм: Папка записи видео ─────────────────────────────────────────
        save_frame = QFrame()
        save_frame.setObjectName("camSection")
        save_frame.setStyleSheet("QFrame#camSection { border: 1px solid #555555; border-radius: 4px; }")
        save_frame_lay = QVBoxLayout(save_frame)
        save_frame_lay.setContentsMargins(8, 8, 8, 8)
        save_frame_lay.setSpacing(8)

        lbl_save = QLabel("Папка записи видео")
        lbl_save.setStyleSheet("font-size: 13px; font-weight: bold;")
        save_frame_lay.addWidget(lbl_save)

        dir_lay = QHBoxLayout()
        self._dir = QLineEdit()
        self._dir.setReadOnly(True)
        self._dir.setText(saved.get("save_dir", os.path.expanduser("~")))
        btn_browse = QPushButton("📁")
        btn_browse.setFixedSize(32, 32)
        btn_browse.clicked.connect(lambda: self._browse(self._dir))
        dir_lay.addWidget(self._dir)
        dir_lay.addWidget(btn_browse)
        save_frame_lay.addLayout(dir_lay)

        btn_save = QPushButton("💾 Сохранить настройки")
        btn_save.setMinimumHeight(36)
        btn_save.setStyleSheet(
            "QPushButton { background: #9b59b6; color: white; font-weight: bold;"
            " border-radius: 4px; } QPushButton:hover { background: #8e44ad; }"
        )
        btn_save.clicked.connect(self._save_settings)
        save_frame_lay.addWidget(btn_save)

        main_row.addWidget(dev_frame,  0, 0)
        main_row.addWidget(save_frame, 1, 0)

        self._grp1, self._dev1, self._res1, self._fps1 = self._make_cam_group_widget("Камера 1", saved.get("cam1", {}))
        self._grp2, self._dev2, self._res2, self._fps2 = self._make_cam_group_widget("Камера 2", saved.get("cam2", {}))

        main_row.addWidget(self._grp1, 0, 1)
        main_row.addWidget(self._grp2, 1, 1)

        root.addLayout(main_row)

    # ── Устройство выбрано в дропдауне ────────────────────────────────────────
    def _on_device_selected(self, _):
        dev_idx = self._cb_devices.currentData()
        if dev_idx is None:
            self._lbl_probe.setText("")
            self._btn_add.setEnabled(False)
            return
        self._lbl_probe.setText("Нажмите «Добавить» для сканирования")
        self._btn_add.setEnabled(not (self._probe_worker and self._probe_worker.isRunning()))

    def _on_probe_done(self, dev_idx: int, dev_name: str, res: list, _fps: list):
        cfg         = load_camera_settings()
        res_fps_map = cfg.get("devices", {}).get(str(dev_idx), {}).get("res_fps_map", {})

        _save(cfg)

        all_fps = sorted({f for fps in res_fps_map.values() for f in fps})
        self._lbl_probe.setText(
            f"✔ Добавлено: {', '.join(res[:3])}{'...' if len(res) > 3 else ''}  |  "
            f"FPS: {', '.join(str(f) for f in all_fps)}"
        )
        self._btn_add.setEnabled(False)
        self.update_devices(self._found)
        cfg2 = load_camera_settings()
        self._fill_dev_combo(self._dev1, cfg2.get("cam1", {}).get("device_id"))
        self._fill_dev_combo(self._dev2, cfg2.get("cam2", {}).get("device_id"))

    def _add_to_config(self):
        """Сканирует выбранное устройство и добавляет в конфиг."""
        dev_idx  = self._cb_devices.currentData()
        dev_name = self._cb_devices.currentText()
        if dev_idx is None:
            return
        if self._probe_worker and self._probe_worker.isRunning():
            return
        self._lbl_probe.setText("⏳ Сканирование возможностей...")
        self._btn_add.setEnabled(False)
        self._probe_worker = _ProbeWorker(dev_idx, dev_name)
        self._probe_worker.done.connect(self._on_probe_done)
        self._probe_worker.start()

    def _reload_cam_group(self, cam_idx: int, cam_cfg: dict):
        cb_dev, lbl_res, lbl_fps = (
            (self._dev1, self._res1, self._fps1) if cam_idx == 0
            else (self._dev2, self._res2, self._fps2)
        )
        self._fill_dev_combo(cb_dev, cam_cfg.get("device_id"))
        self._on_cam_dev_changed(cb_dev, lbl_res, lbl_fps)

    _TITLE_STYLE    = "font-size: 15px; font-weight: bold; color: #1abc9c;"
    _SECTION_STYLE  = "QFrame#section { border: 1px solid #555555; border-radius: 4px; }"

    # ── Группа камеры ─────────────────────────────────────────────────────────
    def _make_cam_group_widget(self, title: str, saved: dict):
        grp, cb_dev, lbl_res, lbl_fps = self._make_cam_group(title, saved, None)
        return grp, cb_dev, lbl_res, lbl_fps

    def _make_cam_group(self, title: str, saved: dict, parent_layout):
        from PyQt6.QtWidgets import QSizePolicy as _SP
        grp = QFrame()
        grp.setObjectName("camSection")
        grp.setStyleSheet("QFrame#camSection { border: 1px solid #555555; border-radius: 4px; }")
        grp.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Preferred)
        grp_lay = QVBoxLayout(grp)
        grp_lay.setContentsMargins(8, 8, 8, 8)
        grp_lay.setSpacing(8)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        grp_lay.addWidget(lbl_title)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        grp_lay.addLayout(form)

        cb_dev = QComboBox()
        form.addRow("Устройство:", cb_dev)

        lbl_res = QLabel("—")
        lbl_res.setStyleSheet("color: gray;")
        form.addRow("Разрешение:", lbl_res)

        lbl_fps = QLabel("—")
        lbl_fps.setStyleSheet("color: gray;")
        form.addRow("Макс. FPS:", lbl_fps)

        self._fill_dev_combo(cb_dev, saved.get("device_id"))
        self._on_cam_dev_changed(cb_dev, lbl_res, lbl_fps)

        cb_dev._last_dev_idx = cb_dev.currentData()
        def _on_dev_changed(_, d=cb_dev, r=lbl_res, f=lbl_fps):
            if d.currentData() != d._last_dev_idx:
                d._last_dev_idx = d.currentData()
                self._on_cam_dev_changed(d, r, f)
        cb_dev.currentIndexChanged.connect(_on_dev_changed)

        if parent_layout is not None:
            parent_layout.addWidget(grp)
        return grp, cb_dev, lbl_res, lbl_fps

    def _fill_dev_combo(self, cb: QComboBox, saved_id=None):
        """Заполняет дропдаун только физически доступными устройствами из конфига."""
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("Не назначена", userData=None)
        cfg = load_camera_settings()
        for dev_id_str, dev_cfg in cfg.get("devices", {}).items():
            dev_id = int(dev_id_str)
            # фильтруем только если уже есть результаты сканирования
            if self._available_ids and dev_id not in self._available_ids:
                continue
            cb.addItem(dev_cfg.get("name", f"Устройство {dev_id_str}"), userData=dev_id)
        if saved_id is not None:
            for i in range(cb.count()):
                if cb.itemData(i) == saved_id:
                    cb.setCurrentIndex(i)
                    break
        cb.blockSignals(False)

    def _on_cam_dev_changed(self, cb_dev: QComboBox, lbl_res: QLabel, lbl_fps: QLabel):
        dev_idx = cb_dev.currentData()
        if dev_idx is None:
            lbl_res.setText("—")
            lbl_fps.setText("—")
            return
        cfg         = load_camera_settings()
        dev_cfg     = cfg.get("devices", {}).get(str(dev_idx), {})
        res_fps_map = dev_cfg.get("res_fps_map", {})
        if res_fps_map:
            max_res = list(res_fps_map.keys())[-1]
            all_fps = sorted({f for v in res_fps_map.values() for f in v})
            lbl_res.setText(max_res)
            lbl_fps.setText(str(max(all_fps)) if all_fps else "—")
        else:
            lbl_res.setText("—")
            lbl_fps.setText("—")

    # ── Обновление списка устройств из сканера ────────────────────────────────
    def update_devices(self, found: list):
        self._found = found
        self._available_ids = {idx for idx, _ in found}
        cfg = load_camera_settings()
        # device_id-ы уже добавленных в конфиг устройств
        in_config = {int(k) for k in cfg.get("devices", {}).keys()}

        # обновляем дропдауны камер — убираем недоступные
        self._fill_dev_combo(self._dev1, cfg.get("cam1", {}).get("device_id"))
        self._fill_dev_combo(self._dev2, cfg.get("cam2", {}).get("device_id"))

        cur = self._cb_devices.currentData()
        self._cb_devices.blockSignals(True)
        self._cb_devices.clear()
        self._cb_devices.addItem("Выберите устройство...", userData=None)
        for idx, name in found:
            if idx not in in_config:
                self._cb_devices.addItem(name, userData=idx)
        if cur is not None:
            for i in range(self._cb_devices.count()):
                if self._cb_devices.itemData(i) == cur:
                    self._cb_devices.setCurrentIndex(i)
                    break
        self._cb_devices.blockSignals(False)
        self._lbl_probe.setText("")
        self._btn_add.setEnabled(False)

    def set_capabilities(self, cam_idx: int, resolutions: list, fps_list: list):
        cb_dev = self._dev1 if cam_idx == 0 else self._dev2
        # уже загружено — не сбрасываем
        if cb_dev.currentData() is not None:
            return
        cfg = load_camera_settings()
        key = "cam1" if cam_idx == 0 else "cam2"
        self._reload_cam_group(cam_idx, cfg.get(key, {}))

    def get_cam_settings(self, cam_idx: int) -> dict:
        cb_dev = self._dev1 if cam_idx == 0 else self._dev2
        return {
            "device_id": cb_dev.currentData(),
            "save_dir":  self._dir.text(),
        }

    def _browse(self, line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку", line_edit.text())
        if folder:
            line_edit.setText(folder)

    def _save_settings(self):
        cfg = load_camera_settings()
        for cam_idx, cb_dev in enumerate([self._dev1, self._dev2]):
            key = "cam1" if cam_idx == 0 else "cam2"
            dev_idx = cb_dev.currentData()
            cfg[key] = {
                "device_id":   dev_idx,
                "device_name": cb_dev.currentText() if dev_idx is not None else "",
            }
        cfg["save_dir"] = self._dir.text()
        _save(cfg)
        self.settings_saved.emit()

    def set_theme(self, dark: bool):
        text   = "#ecf0f1" if dark else "#1a1a1a"
        muted  = "#aaaaaa" if dark else "#666666"
        border = "#555555" if dark else "#cccccc"
        bg     = "#2c2c2c" if dark else "#f5f5f5"

        self.setStyleSheet(f"""
            QGroupBox {{
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                margin-top: 8px;
                font-weight: bold;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
            }}
            QLabel {{ color: {text}; }}
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
        """)
        self._lbl_probe.setStyleSheet(f"color: {muted}; font-size: 11px;")
        if dark:
            self._btn_add.setStyleSheet(
                "QPushButton { background: #2980b9; color: white; font-weight: bold;"
                " border-radius: 4px; min-height: 30px; }"
                "QPushButton:hover { background: #3498db; }"
                "QPushButton:disabled { background: #555; color: #888; }"
            )
        else:
            self._btn_add.setStyleSheet(
                "QPushButton { background: #b0b0b0; color: #1a1a1a; font-weight: bold;"
                " border-radius: 4px; min-height: 30px; }"
                "QPushButton:hover { background: #c8c8c8; }"
                "QPushButton:disabled { background: #d9d9d9; color: #888; }"
            )

    def set_recording(self, recording: bool):
        enabled = not recording
        for w in (self._grp1, self._grp2, self._dev1, self._dev2,
                  self._cb_devices, self._dir):
            w.setEnabled(enabled)
        self._btn_add.setEnabled(enabled and self._btn_add.isEnabled())
