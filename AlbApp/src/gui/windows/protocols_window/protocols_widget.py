"""Вкладка «Протоколы/Журналы» — навигатор по папкам-испытаниям в documents/.

Каждая папка = одно испытание (внутри Протокол.docx и Журнал.docx, создаёт мастер
на шаге «Завершить испытание»). Клик по папке — провалиться внутрь (в пределах
вкладки, без системного проводника), клик по файлу — открыть его Word'ом.
"""
import os
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileIconProvider, QStyle,
)
from PyQt6.QtCore import Qt, QFileInfo, QFileSystemWatcher

# protocols_window → windows → gui → src → AlbApp; documents лежит в AlbApp/documents
_DOCS_DIR = Path(__file__).resolve().parents[4] / "documents"


class ProtocolsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cwd = _DOCS_DIR          # текущая папка навигации (не выходим выше _DOCS_DIR)
        self._history: list = []       # стек посещённых папок для «Назад»
        self._icons = QFileIconProvider()   # нативные иконки Windows (папка, Word для .docx)
        # авто-обновление: следим за текущей папкой, перечитываем при изменениях
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _p: self.reload())

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        bar = QHBoxLayout()
        _st = self.style()

        self._btn_back = QPushButton()
        self._btn_back.setIcon(_st.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self._btn_back.setToolTip("Назад")
        self._btn_back.setFixedWidth(40)
        self._btn_back.clicked.connect(self._go_back)
        self._btn_back.setEnabled(False)
        bar.addWidget(self._btn_back)

        self._btn_up = QPushButton()
        self._btn_up.setIcon(_st.standardIcon(QStyle.StandardPixmap.SP_FileDialogToParent))
        self._btn_up.setToolTip("На уровень выше")
        self._btn_up.setFixedWidth(40)
        self._btn_up.clicked.connect(self._go_up)
        self._btn_up.setEnabled(False)
        bar.addWidget(self._btn_up)

        title = QLabel("Протоколы/Журналы")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #e84393;")
        bar.addWidget(title, 1)

        btn_reload = QPushButton("⟳ Обновить")
        btn_reload.clicked.connect(self.reload)
        bar.addWidget(btn_reload)
        root.addLayout(bar)

        self._tbl = QTableWidget(0, 2)
        self._tbl.setHorizontalHeaderLabels(["Имя", "Дата"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setShowGrid(True)
        self._tbl.setStyleSheet(
            "QTableWidget { gridline-color: #9aa5b1;"
            " border: 2px solid #ffffff; border-radius: 4px; }"
            " QHeaderView::section { background: #e84393; color: #ffffff;"
            " font-weight: bold; padding: 6px 10px;"
            " border: none; border-right: 1px solid #d63384; }")
        self._tbl.setToolTip("Двойной клик: папка — открыть внутри, файл — открыть в Word")
        self._tbl.itemDoubleClicked.connect(self._on_double)
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._tbl, 1)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #9aa5b1;")
        root.addWidget(self._status)

        self.reload()

    def showEvent(self, event):
        # при открытии вкладки — к корню и перечитать
        super().showEvent(event)
        self._cwd = _DOCS_DIR
        self._history.clear()
        self.reload()

    def _enter(self, path: Path):
        """Провалиться в папку (с запоминанием текущей для «Назад»)."""
        self._history.append(self._cwd)
        self._cwd = path
        self.reload()

    def _go_back(self):
        """Вернуться к предыдущей просмотренной папке."""
        if self._history:
            self._cwd = self._history.pop()
            self.reload()

    def _go_up(self):
        """Подняться в родительскую папку (не выше documents/)."""
        if self._cwd != _DOCS_DIR:
            self._history.append(self._cwd)
            self._cwd = self._cwd.parent
            self.reload()

    def _row(self, index: int, path: Path):
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        name_item = QTableWidgetItem(path.name)
        name_item.setIcon(self._icons.icon(QFileInfo(str(path))))   # нативная иконка Windows
        for col, it in ((0, name_item), (1, QTableWidgetItem(date))):
            it.setData(Qt.ItemDataRole.UserRole, str(path))   # путь на обеих ячейках строки
            self._tbl.setItem(index, col, it)

    def reload(self):
        _DOCS_DIR.mkdir(parents=True, exist_ok=True)
        # безопасность: никогда не выходим выше корня documents/
        if not self._cwd.exists() or _DOCS_DIR not in (self._cwd, *self._cwd.parents):
            self._cwd = _DOCS_DIR
        # следим только за текущей папкой (перенаводим watcher при навигации)
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        self._watcher.addPath(str(self._cwd))
        try:
            entries = list(self._cwd.iterdir())
        except OSError as e:
            self._status.setText(f"Ошибка чтения папки: {e}")
            return
        dirs  = sorted((p for p in entries if p.is_dir()),  key=lambda p: p.stat().st_mtime, reverse=True)
        files = sorted((p for p in entries if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)

        sb = self._tbl.verticalScrollBar()
        pos = sb.value()
        self._tbl.setRowCount(0)
        for p in dirs + files:
            i = self._tbl.rowCount(); self._tbl.insertRow(i)
            self._row(i, p)
        sb.setValue(min(pos, sb.maximum()))

        at_root = self._cwd == _DOCS_DIR
        self._btn_up.setEnabled(not at_root)
        self._btn_back.setEnabled(bool(self._history))
        if at_root:
            self._status.setText(f"Испытаний: {len(dirs)}")
        else:
            self._status.setText(f"{self._cwd.name} — файлов: {len(files)}")

    def _on_double(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        p = Path(path)
        if p.is_dir():
            self._enter(p)         # провалиться внутрь папки
        else:
            self._open(str(p))     # открыть файл системным приложением (Word)

    def _open(self, path: str):
        try:
            os.startfile(path)
        except OSError as e:
            self._status.setText(f"Не удалось открыть: {e}")

    def set_theme(self, dark: bool):
        # стиль наследуется из палитры приложения
        pass
