"""Лаунчер: выбор стенда перед открытием приложения.

Показывает стенды из patch/stands.json; «Открыть» запускает на стенд
отдельный процесс приложения (`app.py --stand <id>`) — так два стенда
работают в двух независимых окнах со своими рабочими процессами.

Окна стендов от лаунчера не зависят. На Windows процесс создаётся напрямую
через kernel32.CreateProcessW (см. _spawn_detached_win) под pythonw:
  - без консольного окна (CREATE_NO_WINDOW), своя группа процессов;
  - CREATE_BREAKAWAY_FROM_JOB — выход из Job Object. Отладчик VS Code (debugpy)
    сажает отлаживаемый процесс в job с KILL_ON_JOB_CLOSE: при закрытии
    лаунчера ОС гасит всё дерево, как бы дети ни создавались (ShellExecute
    тоже). Breakaway job разрешает — окно стенда из него выходит;
  - вызов kernel32 через ctypes, а не subprocess: pydevd патчит
    _winapi.CreateProcess и дописывает детям подключение к отладчику.
Вывод окна и его воркера — в stands/<id>/app.log (см. stand.redirect_output_to_log).
Лаунчер можно закрыть, а потом запустить снова, чтобы открыть ещё один
стенд: «Открыт/Открыть» определяется по lock-файлу окна (stand.is_running),
а не по памяти лаунчера.
"""

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox)

import stand


def _spawn_detached_win(exe: str, args: str, cwd: str) -> int:
    """Запустить процесс, не зависящий от лаунчера: без окна консоли, в своей
    группе и вне Job Object родителя (если job это разрешает — иначе без
    breakaway). Окружение наследуется. Возвращает pid."""
    import ctypes
    from ctypes import wintypes

    CREATE_NEW_PROCESS_GROUP  = 0x00000200
    CREATE_NO_WINDOW          = 0x08000000
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    ERROR_ACCESS_DENIED       = 5

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                    ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                    ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                    ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                    ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                    ("hStdError", wintypes.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cmdline = f'"{exe}" {args}'
    base = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    for flags in (base | CREATE_BREAKAWAY_FROM_JOB, base):
        si = STARTUPINFOW(); si.cb = ctypes.sizeof(si)
        pi = PROCESS_INFORMATION()
        # lpCommandLine должен быть изменяемым буфером
        buf = ctypes.create_unicode_buffer(cmdline)
        ok = k32.CreateProcessW(exe, buf, None, None, False, flags, None, cwd,
                                ctypes.byref(si), ctypes.byref(pi))
        if ok:
            k32.CloseHandle(pi.hProcess)
            k32.CloseHandle(pi.hThread)
            return pi.dwProcessId
        err = ctypes.get_last_error()
        if err != ERROR_ACCESS_DENIED:      # breakaway запрещён job'ом → без него
            raise ctypes.WinError(err)
    raise ctypes.WinError(ERROR_ACCESS_DENIED)


class StandPicker(QWidget):
    """Выпадающий список стендов, которые ещё не открыты, и кнопка «Открыть».
    Открытый стенд из списка пропадает (lock-файл пишется сразу при запуске),
    закрытый — возвращается."""

    def __init__(self, app_path: str):
        super().__init__()
        self._app_path = app_path
        self._stands = stand.load_stands()
        self.setWindowTitle("AlbApp — выбор стенда")
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Выберите стенд")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        lay.addWidget(title)
        hint = QLabel("Каждый стенд открывается в своём окне; можно открыть несколько.")
        hint.setStyleSheet("color: #888888;")
        lay.addWidget(hint)

        row = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.setMinimumHeight(34)
        self._combo.currentIndexChanged.connect(self._on_pick)
        row.addWidget(self._combo, 1)
        self._btn_open = QPushButton("Открыть")
        self._btn_open.setFixedSize(110, 34)
        self._btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open.clicked.connect(self._launch)
        row.addWidget(self._btn_open)
        lay.addLayout(row)

        self._lbl_ep = QLabel("")                     # адрес ПЛК выбранного стенда
        self._lbl_ep.setStyleSheet("color: #888888; font-size: 11px;")
        lay.addWidget(self._lbl_ep)
        self._lbl_open = QLabel("")                   # какие стенды уже открыты
        self._lbl_open.setStyleSheet("color: #888888;")
        lay.addWidget(self._lbl_open)
        lay.addStretch()

        self._refresh()
        # закрытые окна возвращаются в список — опрос lock-файлов
        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._refresh)
        self._poll.start()

    def _on_pick(self, _idx: int):
        st = self._combo.currentData()
        self._lbl_ep.setText(st.get("endpoint", "") if st else "")

    def _launch(self):
        st = self._combo.currentData()
        if not st or stand.is_running(st["id"]):
            self._refresh()
            return
        sid = st["id"]
        # в собранном exe sys.executable — само приложение, скрипт не нужен
        frozen = getattr(sys, "frozen", False)
        if sys.platform == "win32":
            # pythonw — окно без консоли; воркер (multiprocessing) берёт тот же
            # исполняемый файл, так что консоль не всплывает и у него
            exe = Path(sys.executable)
            if not frozen:
                pyw = exe.with_name("pythonw.exe")
                exe = pyw if pyw.exists() else exe
            args = f"--stand {sid}" if frozen else f'"{self._app_path}" --stand {sid}'
            pid = _spawn_detached_win(str(exe), args, str(Path(self._app_path).parent))
        else:
            cmd = [sys.executable] + ([] if frozen else [self._app_path]) + ["--stand", sid]
            pid = subprocess.Popen(cmd, start_new_session=True, close_fds=True,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL).pid
        # lock пишем сразу с pid нового процесса — стенд тут же уходит из
        # списка, не дожидаясь, пока окно стартует и пометит себя само
        stand.claim_window(sid, pid)
        self._refresh()

    def _refresh(self):
        opened  = [st for st in self._stands if stand.is_running(st["id"])]
        free    = [st for st in self._stands if st not in opened]
        # список пересобираем только при изменении — иначе ежесекундный
        # clear() сбрасывал бы раскрытый выпадающий список
        ids = [st["id"] for st in free]
        if ids != getattr(self, "_free_ids", None):
            self._free_ids = ids
            cur = self._combo.currentData()
            self._combo.blockSignals(True)
            self._combo.clear()
            for st in free:
                self._combo.addItem(st.get("title", st["id"]), st)
            if cur and cur["id"] in ids:
                self._combo.setCurrentIndex(ids.index(cur["id"]))
            self._combo.blockSignals(False)
            self._on_pick(self._combo.currentIndex())

        none = not free
        self._combo.setEnabled(not none)
        self._btn_open.setEnabled(not none)
        if not self._stands:
            self._lbl_open.setText("В patch/stands.json нет ни одного стенда.")
        elif none:
            self._lbl_open.setText("Все стенды уже открыты.")
        else:
            self._lbl_open.setText(
                "Открыты: " + ", ".join(st.get("title", st["id"]) for st in opened)
                if opened else "")
