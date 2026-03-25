import datetime as _dt  # перевод Unix-timestamp в человекочитаемое время для меток оси
import pyqtgraph as pg  # базовый класс AxisItem, который мы переопределяем


class _TimeAxisItem(pg.AxisItem):
    """Ось X с метками в формате ЧЧ:ММ:СС (или дд.мм ЧЧ:ММ для больших диапазонов)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ts_offset: float = 0.0  # прибавляется к нормализованному x → реальный timestamp

    def tickStrings(self, values, scale, spacing):  # noqa: ARG002
        result = []
        for v in values:
            try:
                dt = _dt.datetime.fromtimestamp(v + self.ts_offset)
                if spacing >= 86400:          # диапазон > суток → дд.мм ЧЧ:ММ
                    result.append(dt.strftime("%d.%m\n%H:%M"))
                elif spacing >= 3600:         # диапазон > часа → ЧЧ:ММ
                    result.append(dt.strftime("%H:%M"))
                elif spacing >= 1:            # секунды → ЧЧ:ММ:СС
                    result.append(dt.strftime("%H:%M:%S"))
                else:                         # миллисекунды
                    result.append(dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}")
            except (OSError, ValueError, OverflowError):
                result.append("")
        return result
