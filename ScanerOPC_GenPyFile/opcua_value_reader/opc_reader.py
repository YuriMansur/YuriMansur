import sys
import asyncio

from asyncua import Client
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit
)
from button import OpcUaButton
from PyQt6.QtCore import QThread, pyqtSignal


class OpcWorkerThread(QThread):
    """
    Один поток, один asyncio.run(), один Client.
    GUI отправляет команды через put_command() → asyncio.Queue внутри потока.
    """
    message = pyqtSignal(str)

    _STOP = object()

    def __init__(self):
        super().__init__()
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- вызывается из GUI потока ---

    def put_command(self, cmd: dict):
        """Отправить команду в очередь потока (thread-safe)."""
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, cmd)

    def stop(self):
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, self._STOP)

    # --- event loop потока ---

    def run(self):
        asyncio.run(self._main())

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._sub = None

        while True:
            cmd = await self._queue.get()

            if cmd is self._STOP:
                break

            url     = cmd.get("url", "")
            node_id = cmd.get("node_id", "")
            action  = cmd.get("action")

            if action == "read":
                asyncio.create_task(self._read(url, node_id))

            elif action == "write":
                asyncio.create_task(self._write(url, node_id, cmd["value"]))

            elif action == "subscribe":
                asyncio.create_task(self._subscribe(url, node_id, cmd.get("interval", 500)))

            elif action == "unsubscribe":
                asyncio.create_task(self._unsubscribe())

    # --- async операции ---

    async def _read(self, url, node_id):
        try:
            async with Client(url=url) as client:
                value = await client.get_node(node_id).read_value()
                self.message.emit(f"[{node_id}] = {value}")
        except Exception as e:
            self.message.emit(f"Ошибка чтения: {e}")

    async def _write(self, url, node_id, value):
        try:
            async with Client(url=url) as client:
                await client.get_node(node_id).write_value(value)
                self.message.emit(f"[{node_id}] записано: {value}")
        except Exception as e:
            self.message.emit(f"Ошибка записи: {e}")

    async def _subscribe(self, url, node_id, interval):
        await self._unsubscribe()
        try:
            emit = self.message.emit

            class _Handler:
                def datachange_notification(self, _node, val, _data):
                    emit(f"[{node_id}] = {val}")

            self._sub_client = Client(url=url)
            await self._sub_client.connect()
            self._sub = await self._sub_client.create_subscription(interval, _Handler())
            await self._sub.subscribe_data_change(self._sub_client.get_node(node_id))
            self.message.emit(f"Подписка активна: {node_id}")
        except Exception as e:
            self._sub = None
            self.message.emit(f"Ошибка подписки: {e}")

    async def _unsubscribe(self):
        if self._sub:
            try:
                await self._sub.delete()
            except Exception:
                pass
            self._sub = None
        if hasattr(self, "_sub_client") and self._sub_client:
            try:
                await self._sub_client.disconnect()
            except Exception:
                pass
            self._sub_client = None
            self.message.emit("Подписка отменена.")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPC UA Reader")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        for label, placeholder, attr in [
            ("Адрес сервера:", "opc.tcp://192.168.6.6:4840", "url_edit"),
            ("Node ID:", "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.read_control_mode", "node_edit"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            edit = QLineEdit(placeholder)
            row.addWidget(edit)
            setattr(self, attr, edit)
            layout.addLayout(row)

        btn_row = QHBoxLayout()
        self.read_btn = OpcUaButton("Читать")
        self.read_btn.clicked.connect(self._on_read)
        btn_row.addWidget(self.read_btn)
        self.sub_btn = OpcUaButton("Подписаться", active_text="Отписаться")
        self.sub_btn.clicked.connect(self._on_subscribe)
        btn_row.addWidget(self.sub_btn)
        layout.addLayout(btn_row)

        write_row = QHBoxLayout()
        write_row.addWidget(QLabel("Значение:"))
        self.write_edit = QLineEdit()
        write_row.addWidget(self.write_edit)
        self.write_btn = OpcUaButton("Записать")
        self.write_btn.clicked.connect(self._on_write)
        write_row.addWidget(self.write_btn)
        layout.addLayout(write_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        layout.addWidget(self.log)

        self._worker = OpcWorkerThread()
        self._worker.message.connect(self.log.append)
        self._worker.start()
        self._subscribed = False

    def _cmd(self, **kwargs) -> dict:
        return {"url": self.url_edit.text(), "node_id": self.node_edit.text(), **kwargs}

    def _on_read(self):
        self._worker.put_command(self._cmd(action="read"))

    def _on_write(self):
        raw = self.write_edit.text()
        for cast in (int, float):
            try:
                raw = cast(raw)
                break
            except ValueError:
                pass
        self._worker.put_command(self._cmd(action="write", value=raw))

    def _on_subscribe(self):
        if not self._subscribed:
            self._worker.put_command(self._cmd(action="subscribe"))
        else:
            self._worker.put_command({"action": "unsubscribe"})
        self._subscribed = not self._subscribed
        self.sub_btn.set_active(self._subscribed)

    def closeEvent(self, event):
        self._worker.stop()
        self._worker.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
