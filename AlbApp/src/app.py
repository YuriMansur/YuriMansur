import os
import sys
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))           # src/
sys.path.insert(0, str(Path(__file__).parent.parent))    # AlbApp/


def _stand_arg() -> str | None:
    """`--stand <id>` из командной строки (так лаунчер запускает окно стенда)."""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--stand" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--stand="):
            return a.split("=", 1)[1]
    return None


def run_launcher(app):
    """Окно выбора стенда: на каждый выбранный — отдельный процесс app.py --stand."""
    from gui.popups.stand_picker import StandPicker
    picker = StandPicker(app_path=str(Path(__file__).resolve()))
    picker.show()
    return app.exec()


def run_stand(app, stand_id: str):
    """Главное окно одного стенда со своим рабочим процессом (OPC UA + Influx)."""
    import stand
    # до старта воркера: рабочий процесс наследует ALB_STAND и читает тот же стенд
    stand.set_current(stand_id)
    stand.redirect_output_to_log()   # под pythonw — вывод в stands/<id>/app.log
    # lock с чужим живым pid — стенд уже открыт другим окном. Свой pid в lock —
    # норма: лаунчер записывает его сразу при запуске, не дожидаясь нас. Pid
    # родителя — тоже «свой»: python.exe из venv на Windows — стаб, который
    # запускает настоящий интерпретатор дочерним процессом (лаунчер видит стаб)
    other = stand.window_pid(stand_id)
    if other is not None and other not in (os.getpid(), os.getppid()):
        print(f"[stand] окно стенда {stand_id} уже открыто (pid {other})")
        return 0
    stand.claim_window()          # lock-файл с pid — по нему лаунчер видит «открыт»

    from gui.windows.main_window import MainWindow
    from ipc_bridge import IpcBridge
    from worker_process.main import worker_main

    # Очереди IPC между GUI-процессом и рабочим процессом
    live_q = multiprocessing.Queue()  # worker → GUI: live-данные и статус
    cmd_q  = multiprocessing.Queue()  # GUI → worker: команды записи тегов

    # Рабочий процесс: OPC UA + кольцевой буфер + InfluxDB (свой GIL)
    worker = multiprocessing.Process(
        target  = worker_main,
        args    = (live_q, cmd_q),
        daemon  = True,
        name    = f"AlbWorker-{stand_id}",
    )
    worker.start()

    # Мост: дренирует live_q → bus-сигналы; bus.cmd_* → cmd_q
    bridge = IpcBridge(live_q, cmd_q, parent=app)

    app.aboutToQuit.connect(bridge.stop)
    app.aboutToQuit.connect(worker.terminate)
    app.aboutToQuit.connect(stand.release_window)

    window = MainWindow()
    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    multiprocessing.freeze_support()  # нужно для Windows при сборке в exe

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    stand_id = _stand_arg()
    # без --stand — лаунчер с выбором стенда; с --stand — окно этого стенда
    sys.exit(run_launcher(app) if stand_id is None else run_stand(app, stand_id))
