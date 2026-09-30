"""calc.py — расчётные формулы ГОСТ для стенда (чистая математика, без Qt).

Интерполяция смещений f и o для сечения X между базовыми плоскостями
K (коленная, верхняя) и A (голеностопная, нижняя) по координате u:

    f_X = f_K + (f_K − f_A)(u_X − u_K) / (u_K − u_A)
    o_X = o_K + (o_K − o_A)(u_X − u_K) / (u_K − u_A)

u_X — длина сегмента, введённая оператором на шаге «Установка образца»
(поля seg_upper / seg_lower); считается отдельно для верхнего и нижнего
сегмента. u_K = 500, u_A = 80 — константы. Смещения в базовых плоскостях
f_K, o_K, f_A, o_A зависят от уровня нагрузки (P3/P4/P5) и условия
нагружения (I/II) — таблица 6 ГОСТ Р ИСО 10328-2021, лежит в
patch/gost_config.json → "displacements".
"""

import math
from dataclasses import dataclass

import param_config

# ── константы базовых плоскостей ──────────────────────────────────────────────
U_K = 500.0   # координата коленной плоскости K, мм
U_A = 80.0    # координата голеностопной плоскости A, мм


@dataclass(frozen=True)
class FO:
    """Смещения сечения: f и o, мм."""
    f: float
    o: float

    @property
    def resultant(self) -> float:
        """Результирующее смещение √(f² + o²)."""
        return math.hypot(self.f, self.o)

    @property
    def angle(self) -> float:
        """Угол arctg(o / f), градусы. При f = 0 — ±90° по знаку o."""
        if self.f == 0:
            return math.copysign(90.0, self.o) if self.o else 0.0
        return math.degrees(math.atan(self.o / self.f))


def base_planes(level: str, cond: str) -> dict[str, FO] | None:
    """Смещения f, o в базовых плоскостях T/K/A/B для уровня нагрузки и
    условия нагружения (таблица 6). None — для этой пары таблицы нет
    (например, P6…P8)."""
    table = param_config._config().get("displacements", {}).get("values", {})
    row = table.get(level, {}).get(cond)
    if not row:
        return None
    return {plane: FO(float(f), float(o)) for plane, (f, o) in row.items()}


def interp_from_k(u_x: float, v_k: float, v_a: float,
                  u_k: float = U_K, u_a: float = U_A) -> float:
    """Линейная интерполяция величины v (f или o) от плоскости K:
    v_X = v_K + (v_K − v_A)(u_X − u_K) / (u_K − u_A)."""
    return v_k + (v_k - v_a) * (u_x - u_k) / (u_k - u_a)


def segment_fo(u_x: float, k: FO, a: FO,
               u_k: float = U_K, u_a: float = U_A) -> FO:
    """f_X и o_X для сечения на координате u_x (длина сегмента) при заданных
    смещениях в плоскостях K и A."""
    return FO(f=interp_from_k(u_x, k.f, a.f, u_k, u_a),
              o=interp_from_k(u_x, k.o, a.o, u_k, u_a))


def segments_fo(seg_upper: float, seg_lower: float,
                level: str, cond: str) -> dict[str, FO] | None:
    """Расчёт для обоих сегментов образца по уровню нагрузки и условию:
    {"upper": FO, "lower": FO}. None — если для (level, cond) нет таблицы.

    Длина нижнего сегмента в большинстве случаев 0 — это обычное значение
    u_X, считается как все: при u_X = 0 формула даёт смещения нижней
    плоскости B из таблицы 6 (например P5/I: f = −48, o = 45)."""
    planes = base_planes(level, cond)
    if planes is None:
        return None
    k, a = planes["K"], planes["A"]
    return {"upper": segment_fo(seg_upper, k, a),
            "lower": segment_fo(seg_lower, k, a)}


# ── прочие формулы (перенесены из special_calc.py) ────────────────────────────
def scale_force(F: float, s_child: float, s_adult: float) -> float:
    """Пересчёт силы по соотношению размеров: F · S_child / S_adult."""
    return F * (s_child / s_adult)


def Fc(t: float, F_cmax: float) -> float:
    """Циклическая нагрузка F_c(t) = F_cmax · 10⁻³ · poly(t), схема Горнера."""
    poly = t * (3.62495690883228
         + t * (1.64651497111425e-1
         + t * (-1.67101914899229e-3
         + t * (5.98882225167948e-6
         + t * (-9.20373741104191e-9
         + t *   5.12306842296552e-12)))))
    return F_cmax * 1e-3 * poly
