"""Фоновая обработка записанного видео: врезает график трендов в каждый кадр.

Синхронизация — по сайдкару rec_*.csv (реальное UTC-время каждого кадра),
который пишется во время записи в section1._CameraWidget. Данные тянутся из
InfluxDB за длительность записи, график рисуется средствами cv2.
"""
import os
import re

import numpy as np
import pandas as pd
import cv2
from PyQt6.QtCore import QThread, pyqtSignal

from gui.windows.trengs_window._archive_worker import (
    INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET, LIVE_WINDOW_SECS,
)

# (measurement, field, name, hex-цвет, ступенчатая ли линия) — порядок и цвета
# совпадают с живым графиком трендов (TrendsWiget).
CHANNELS = [
    ("nowSetpoint",  "value", "Текущая уставка нагружения", "#e67e22", True),
    ("tenza",        "value", "Датчик нагружения",          "#3498db", False),
    ("displacement", "value", "Датчик перемещения",         "#2ecc71", False),
]


def _hex_to_bgr(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def _find_sidecar(video_path: str) -> str:
    """Путь к таблице «кадр → время» для ролика.

    Сначала ищем рядом одноимённый .csv, затем — общий для обеих камер: их
    ролики называются `rec_<стамп>_cam1.avi` / `_cam2.avi`, а сайдкар на них
    один — `rec_<стамп>.csv`. Возвращаем найденный путь, иначе одноимённый
    (по нему выше выводится сообщение «нет сайдкара»).
    """
    stem = os.path.splitext(video_path)[0]
    own = stem + ".csv"
    if os.path.exists(own):
        return own
    m = re.match(r"^(.*)_cam\d+$", stem)
    if m:
        shared = m.group(1) + ".csv"
        if os.path.exists(shared):
            return shared
    return own


def _render_label_bgra(text: str, rgb: tuple, font_px: int = 13) -> np.ndarray:
    """Отрисовать строку (в т.ч. кириллицу) в BGRA-массив через QPainter.

    Вызывается несколько раз до цикла кадров — результат кэшируется.
    """
    from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QFontMetrics
    from PyQt6.QtCore import Qt

    font = QFont("Segoe UI", -1)
    font.setPixelSize(font_px)
    font.setBold(True)
    fm = QFontMetrics(font)
    w = fm.horizontalAdvance(text) + 4
    h = fm.height() + 2

    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(0)
    p = QPainter(img)
    p.setFont(font)
    p.setPen(QColor(rgb[0], rgb[1], rgb[2]))
    p.drawText(2, fm.ascent() + 1, text)
    p.end()

    ptr = img.constBits()
    ptr.setsize(h * w * 4)
    rgba = np.frombuffer(ptr, np.uint8).reshape(h, w, 4)
    bgra = rgba[:, :, [2, 1, 0, 3]].copy()   # RGBA → BGRA
    return bgra


def _blit_bgra(dst: np.ndarray, patch: np.ndarray, x: int, y: int) -> None:
    """Наложить BGRA-патч на BGR-кадр с учётом альфы (с обрезкой по границам)."""
    ph, pw = patch.shape[:2]
    H, W = dst.shape[:2]
    if x >= W or y >= H or x + pw <= 0 or y + ph <= 0:
        return
    sx, sy = max(0, -x), max(0, -y)
    ex, ey = min(pw, W - x), min(ph, H - y)
    dx, dy = x + sx, y + sy
    sub = patch[sy:ey, sx:ex]
    a = sub[:, :, 3:4].astype(np.float32) / 255.0
    roi = dst[dy:dy + (ey - sy), dx:dx + (ex - sx)]
    roi[:] = (roi * (1 - a) + sub[:, :, :3] * a).astype(np.uint8)


class OverlayWorker(QThread):
    progress    = pyqtSignal(int, str)   # процент 0..100, сообщение статуса
    file_done   = pyqtSignal(str)        # путь готового файла
    finished_ok = pyqtSignal(list)       # список всех готовых файлов
    failed      = pyqtSignal(str)        # текст ошибки (фатальной для всего батча)

    def __init__(self, files: list, opts: dict, parent=None):
        super().__init__(parent)
        self._files = files
        self._opts  = opts
        self._abort = False

    def abort(self):
        self._abort = True

    # ── загрузка данных из Influx ──────────────────────────────────────────────

    def _query_channel(self, client, measurement, field, t_from, t_to):
        def _iso(ts):
            import datetime as _dt
            return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {_iso(t_from)}, stop: {_iso(t_to)})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}")
  |> keep(columns: ["_time", "_value"])
'''
        df = client.query_api().query_data_frame(query)
        if isinstance(df, list):
            df = pd.concat(df, ignore_index=True) if df else None
        if df is None or len(df) == 0 or "_value" not in df.columns:
            return np.empty(0), np.empty(0)
        t = df["_time"].to_numpy(dtype="datetime64[ns]").astype("int64") / 1e9
        v = df["_value"].to_numpy(dtype=np.float64)
        order = np.argsort(t, kind="stable")
        return t[order], v[order]

    def _fake_timestamps(self, video_path):
        """Демо без сайдкара: время кадров из числа кадров и fps видео."""
        import time
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            cap.release()
            return None
        n   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.release()
        if n <= 0:
            return None
        t0 = time.time() - n / fps     # чтобы метка времени на оверлее была «свежей»
        return t0 + np.arange(n) / fps

    def _synthetic_series(self, t0, t_end, enabled):
        """Демо-данные на диапазон записи: ступенька / синус / пандус.

        Формат как у Influx-ветки: список (times, values, hex-цвет, step) или None.
        Периоды масштабируются под длину записи, чтобы график был наглядным.
        """
        dur = max(t_end - t0, 1.0)
        td  = np.arange(0, dur, 0.02)        # 50 Гц
        T   = t0 + td
        gens = [
            np.floor(td / (dur / 8)) * 12.5,             # уставка — ступенька (8 шагов)
            60 + 45 * np.sin(2 * np.pi * td / (dur / 4)),  # нагружение — синус (4 периода)
            td / dur * 100.0,                            # перемещение — пандус
        ]
        out = []
        for idx, (meas, field, name, color, step) in enumerate(CHANNELS):
            if not enabled[idx]:
                out.append(None)
                continue
            out.append((T, gens[idx].astype(np.float64), color, step))
        return out

    # ── главный цикл ────────────────────────────────────────────────────────────

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")

    def _run(self):
        from influxdb_client import InfluxDBClient

        win_secs   = float(self._opts.get("window_secs", LIVE_WINDOW_SECS))
        size_pct   = float(self._opts.get("size_pct", 33)) / 100.0
        opacity    = float(self._opts.get("opacity", 60)) / 100.0
        position   = self._opts.get("position", "br")
        enabled    = self._opts.get("channels", [True, True, True])

        done_files = []

        for fi, video_path in enumerate(self._files):
            if self._abort:
                break
            base = os.path.basename(video_path)
            sidecar = _find_sidecar(video_path)
            demo = self._opts.get("demo")
            if os.path.exists(sidecar):
                ts = pd.read_csv(sidecar)["timestamp"].to_numpy(dtype=np.float64)
                if len(ts) == 0:
                    self.progress.emit(0, f"⚠ {base}: пустой сайдкар — пропуск")
                    continue
            elif demo:
                # демо без сайдкара: время кадров синтезируем из самого видео
                ts = self._fake_timestamps(video_path)
                if ts is None:
                    self.progress.emit(0, f"⚠ {base}: не открыть видео — пропуск")
                    continue
            else:
                self.progress.emit(0, f"⚠ {base}: нет сайдкара {os.path.basename(sidecar)} — пропуск")
                continue
            t0, t_end = float(ts[0]), float(ts[-1])

            if self._opts.get("demo"):
                # синтетика вместо Influx — посмотреть наложение без живых данных
                self.progress.emit(0, f"[{fi + 1}/{len(self._files)}] {base}: демо-данные…")
                series = self._synthetic_series(t0, t_end, enabled)
            else:
                self.progress.emit(0, f"[{fi + 1}/{len(self._files)}] {base}: запрос данных…")
                # timeout (мс) — чтобы недоступная/медленная база не подвешивала обработку
                client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG,
                                        enable_gzip=True, timeout=30_000)
                series = []
                try:
                    for idx, (meas, field, name, color, step) in enumerate(CHANNELS):
                        if not enabled[idx]:
                            series.append(None)
                            continue
                        ct, cv = self._query_channel(client, meas, field, t0 - win_secs, t_end + 2)
                        series.append((ct, cv, color, step))
                except Exception as e:
                    self.progress.emit(0, f"⚠ {base}: ошибка запроса к Influx ({e}) — пропуск")
                    continue
                finally:
                    client.close()

            # общий Y-диапазон по всем включённым каналам (фикс — без скачков по кадрам)
            all_v = [s[1] for s in series if s is not None and len(s[1])]
            if not all_v:
                self.progress.emit(0, f"⚠ {base}: нет данных в Influx за период записи — пропуск")
                continue
            allv = np.concatenate(all_v)
            ymin, ymax = float(allv.min()), float(allv.max())
            span = (ymax - ymin) or abs(ymax) or 1.0
            ymin, ymax = ymin - span * 0.05, ymax + span * 0.05

            # в демо окно ограничиваем длиной записи — иначе короткий ролик
            # прижмёт всю синтетику к правому краю
            eff_win = min(win_secs, t_end - t0) if self._opts.get("demo") else win_secs

            out_path = self._process_video(
                video_path, ts, series, eff_win, size_pct, opacity, position,
                ymin, ymax, fi, len(self._files), base,
            )
            if out_path:
                done_files.append(out_path)
                self.file_done.emit(out_path)

        if not self._abort:
            self.finished_ok.emit(done_files)

    def _process_video(self, video_path, ts, series, win_secs, size_pct, opacity,
                        position, ymin, ymax, fi, nfiles, base):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.progress.emit(0, f"⚠ {base}: не открыть видео — пропуск")
            return None
        fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
        W      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total  = len(ts)

        # геометрия панели графика
        ow = max(160, int(W * size_pct))
        oh = max(100, int(ow * 0.6))
        margin = max(8, W // 100)
        if position == "br":
            x0, y0 = W - ow - margin, H - oh - margin
        elif position == "bl":
            x0, y0 = margin, H - oh - margin
        elif position == "tr":
            x0, y0 = W - ow - margin, margin
        else:  # tl
            x0, y0 = margin, margin
        x1, y1 = x0 + ow, y0 + oh

        # Подписи каналов пришли уже отрисованными (в GUI-потоке, см. виджет) —
        # здесь только масштабируем под ширину панели. Никакого Qt в рабочем потоке:
        # рисование QPainter вне GUI-потока на Windows может зависнуть.
        labels_hires = self._opts.get("labels_hires") or [None] * len(series)
        base_px = self._opts.get("label_base_px", 40)
        font_px = max(11, min(18, ow // 26))   # длинные имена должны влезать, сверху кап
        scale = font_px / base_px
        labels = []
        for idx, s in enumerate(series):
            lbl = None if s is None else labels_hires[idx]
            if lbl is not None:
                lbl = cv2.resize(lbl, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            labels.append(lbl)
        row_h = max([l.shape[0] for l in labels if l is not None], default=font_px + 3) + 1

        out_path = os.path.splitext(video_path)[0] + "_chart.avi"
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(out_path, fourcc, fps, (W, H))

        i = 0
        while True:
            if self._abort:
                break
            ok, frame = cap.read()
            if not ok:
                break
            t = float(ts[i]) if i < total else float(ts[-1])
            self._draw_overlay(frame, t, series, labels, row_h, win_secs,
                               x0, y0, x1, y1, ymin, ymax, opacity, font_px)
            writer.write(frame)
            i += 1
            if i % 25 == 0 or i == total:
                pct = int(i / max(total, 1) * 100)
                self.progress.emit(pct, f"[{fi + 1}/{nfiles}] {base}: кадр {i}/{total}")

        cap.release()
        writer.release()
        if self._abort:
            try:
                os.remove(out_path)
            except OSError:
                pass
            return None
        return out_path

    # ── отрисовка одного оверлея ──────────────────────────────────────────────

    def _draw_overlay(self, frame, t, series, labels, row_h, win_secs,
                      x0, y0, x1, y1, ymin, ymax, opacity, font_px=14):
        # Цифры набираем векторным шрифтом OpenCV: у него на масштабе 1.0 высота
        # прописной ≈ 22 px, отсюда пересчёт из font_px. Так значения выходят
        # вровень с названиями каналов, а не вдвое мельче, как было.
        val_sc  = font_px / 24.0
        time_sc = font_px / 28.0
        thick   = 2 if font_px >= 17 else 1

        # фон панели (полупрозрачный тёмный)
        roi = frame[y0:y1, x0:x1]
        bg = np.full_like(roi, (40, 40, 40))
        frame[y0:y1, x0:x1] = cv2.addWeighted(roi, 1 - opacity, bg, opacity, 0)

        pad = 8
        px0, py0 = x0 + pad, y0 + pad
        px1, py1 = x1 - pad, y1 - (font_px + 8)   # снизу место под метку времени
        pw, ph = px1 - px0, py1 - py0
        if pw < 10 or ph < 10:
            return

        # рамка и горизонтальная сетка
        cv2.rectangle(frame, (px0, py0), (px1, py1), (90, 90, 90), 1)
        for k in range(1, 4):
            gy = py0 + ph * k // 4
            cv2.line(frame, (px0, gy), (px1, gy), (70, 70, 70), 1)

        t_left = t - win_secs
        yspan = (ymax - ymin) or 1.0

        # кривые
        for s in series:
            if s is None:
                continue
            ct, cv, color, step = s
            if len(ct) == 0:
                continue
            lo = int(np.searchsorted(ct, t_left, "left"))
            hi = int(np.searchsorted(ct, t, "right"))
            lo = max(0, lo - 1)          # одна точка слева — линия входит от края
            if hi - lo < 1:
                continue
            wt, wv = ct[lo:hi], cv[lo:hi]

            # прореживание до ~2 точек на пиксель ширины
            maxpts = pw * 2
            if len(wt) > maxpts:
                sel = np.linspace(0, len(wt) - 1, maxpts).astype(np.int64)
                wt, wv = wt[sel], wv[sel]

            xs = px0 + ((wt - t_left) / win_secs * pw)
            ys = py1 - ((wv - ymin) / yspan * ph)
            np.clip(xs, px0, px1, out=xs)
            np.clip(ys, py0, py1, out=ys)

            if step and len(wt) > 1:
                # ступенчатая линия: дублируем точки (как уставка в трендах)
                xs = np.repeat(xs, 2)[1:]
                ys = np.repeat(ys, 2)[:-1]

            pts = np.column_stack([xs, ys]).astype(np.int32)
            cv2.polylines(frame, [pts], False, _hex_to_bgr(color), 1, cv2.LINE_AA)

        # курсор «сейчас» — правый край окна
        cv2.line(frame, (px1, py0), (px1, py1), (150, 150, 150), 1, cv2.LINE_AA)

        # легенда: цвет-образец + название (кириллица из кэша) + текущее значение
        ly = py0 + 2
        for s, lbl in zip(series, labels):
            if s is None:
                continue
            ct, cv, color, step = s
            cur = ""
            if len(ct):
                j = int(np.searchsorted(ct, t, "right")) - 1
                if j >= 0:
                    cur = f"  {cv[j]:.2f}"
            # образец цвета — по середине строки, чтобы не уезжал от крупных цифр
            sy = ly + row_h // 2
            cv2.line(frame, (px0 + 4, sy), (px0 + 18, sy), _hex_to_bgr(color), thick)
            lx = px0 + 24
            if lbl is not None:
                _blit_bgra(frame, lbl, lx, ly)
                lx += lbl.shape[1]
            if cur:
                cv2.putText(frame, cur, (lx, ly + font_px), cv2.FONT_HERSHEY_SIMPLEX,
                            val_sc, _hex_to_bgr(color), thick, cv2.LINE_AA)
            ly += row_h

        # метка времени текущего кадра (ASCII)
        import datetime as _dt
        tstr = _dt.datetime.fromtimestamp(t).strftime("%H:%M:%S")
        cv2.putText(frame, tstr, (px0, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    time_sc, (210, 210, 210), 1, cv2.LINE_AA)
