"""Главное окно StandPatcher: кнопки стендов + лог подкладки конфигов."""
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QPlainTextEdit, QFrame, QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor

import patcher

_ACCENT = "#1abc9c"
_GREEN = "#27ae60"
_RED = "#c0392b"
_MUTED = "#9aa3ad"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StandPatcher")
        self.setMinimumSize(720, 620)
        self.cfg = patcher.load_config()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_stands(), 1)
        root.addWidget(self._build_log(), 1)

        self._apply_style()
        self._refresh_target_status()

    # ── шапка: целевой каталог AlbApp + статус ──────────────────────────────
    def _build_header(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 10)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Целевой каталог AlbApp")
        t.setObjectName("muted")
        self._lbl_path = QLabel(str(patcher.albapp_root(self.cfg)))
        self._lbl_path.setObjectName("path")
        self._lbl_path.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(self._lbl_path)
        lay.addLayout(col, 1)

        self._lbl_status = QLabel("")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._lbl_status, 0)
        return f

    # ── сетка кнопок стендов, сгруппированных по «group» ────────────────────
    def _build_stands(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        groups: dict[str, list[dict]] = {}
        for st in self.cfg["stands"]:
            groups.setdefault(st.get("group", "Стенды"), []).append(st)

        for gname, stands in groups.items():
            gl = QLabel(gname)
            gl.setObjectName("group")
            outer.addWidget(gl)
            grid = QGridLayout()
            grid.setSpacing(8)
            for i, st in enumerate(stands):
                b = QPushButton(st["name"])
                b.setObjectName("stand")
                b.setMinimumHeight(44)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _c=False, s=st: self._on_stand(s))
                grid.addWidget(b, 0, i)
            outer.addLayout(grid)

        outer.addStretch()
        scroll.setWidget(host)
        return scroll

    # ── панель лога ─────────────────────────────────────────────────────────
    def _build_log(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Лог подкладки")
        title.setObjectName("group")
        head.addWidget(title, 1)
        btn_clear = QPushButton("Очистить")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(lambda: self._log.clear())
        head.addWidget(btn_clear, 0)
        lay.addLayout(head)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("log")
        lay.addWidget(self._log, 1)
        return f

    # ── обработка нажатия на стенд ──────────────────────────────────────────
    def _on_stand(self, stand: dict):
        if not patcher.albapp_root(self.cfg).exists():
            QMessageBox.critical(self, "StandPatcher",
                                 "Целевой каталог AlbApp не найден.\n"
                                 "Проверьте путь albapp_root в stands_config.json.")
            return
        resp = QMessageBox.question(
            self, "Подложить конфиги",
            f"Заменить конфиги текущей программы набором «{stand['name']}»?\n"
            "Существующие файлы будут перезаписаны.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        self._append(f"[{ts}] ═══ {stand['name']} ═══", color=_ACCENT, bold=True)
        results = patcher.patch_stand(stand, self.cfg)
        ok_n = sum(1 for ok, _ in results if ok)
        for ok, msg in results:
            self._append(("  ✓ " if ok else "  ✕ ") + msg, color=_GREEN if ok else _RED)
        fail = len(results) - ok_n
        summary = f"  Итого: заменено {ok_n}" + (f", ошибок {fail}" if fail else "")
        self._append(summary, color=_MUTED, bold=True)
        self._append("")

    # ── вывод строки в лог с цветом ─────────────────────────────────────────
    def _append(self, text: str, color: str = "#dce3ea", bold: bool = False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            from PyQt6.QtGui import QFont
            fmt.setFontWeight(QFont.Weight.Bold)
        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(text + "\n", fmt)
        self._log.setTextCursor(cur)
        self._log.ensureCursorVisible()

    def _refresh_target_status(self):
        ok = patcher.albapp_root(self.cfg).exists()
        self._lbl_status.setText("● найден" if ok else "● не найден")
        self._lbl_status.setStyleSheet(f"color: {_GREEN if ok else _RED}; font-weight: bold;")

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget {{ background: #1f242b; color: #dce3ea; font-size: 13px; }}
            QFrame#card {{ background: #262c34; border: 1px solid #333b45; border-radius: 8px; }}
            QLabel#muted {{ color: {_MUTED}; font-size: 11px; }}
            QLabel#path {{ color: #dce3ea; font-weight: bold; }}
            QLabel#group {{ color: {_ACCENT}; font-size: 13px; font-weight: bold;
                            letter-spacing: 0.5px; padding-top: 4px; }}
            QPushButton {{ background: #313944; color: #dce3ea; border: 1px solid #3d4753;
                           border-radius: 6px; padding: 6px 12px; }}
            QPushButton:hover {{ background: #3a4350; }}
            QPushButton#stand {{ font-weight: bold; }}
            QPushButton#stand:hover {{ border-color: {_ACCENT}; }}
            QPlainTextEdit#log {{ background: #15191e; border: 1px solid #333b45;
                                  border-radius: 6px; font-family: Consolas, monospace;
                                  font-size: 12px; padding: 6px; }}
        """)
