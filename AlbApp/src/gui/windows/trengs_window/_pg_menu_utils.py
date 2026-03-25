import datetime as _dt          # форматирование временны́х меток в полях диапазона оси X
import pyqtgraph as pg            # доступ к ViewBox, ViewBoxMenu и PlotItem для модификации меню
from PyQt6.QtGui import QAction   # пункты меню «CSV» / «Excel» в подменю Экспорт


def _translate_pg_menus(plot_widget):
    """Переводит контекстное меню pyqtgraph на русский."""
    vb = plot_widget.getViewBox()
    m  = vb.menu   # ViewBoxMenu

    # ── ViewBox: верхний уровень ──────────────────────────────
    m.viewAll.setVisible(False)
    m.mouseModes[0].setText("3 кнопки (панорама)")
    m.mouseModes[1].setText("1 кнопка (выделение)")

    # Режим мыши: 3 кнопки (панорама) по умолчанию, убрать из меню
    vb.setMouseMode(pg.ViewBox.PanMode)

    # ── ViewBox: подменю осей → перенести в "Масштаб" ────────
    _sub_ru = {"X axis": "Ось X", "Y axis": "Ось Y"}
    axis_actions = []
    for action in m.actions():
        if action.menu():
            if action.text() in _sub_ru:
                ru_title = _sub_ru[action.text()]
                action.menu().setTitle(ru_title)
                axis_actions.append((action, ru_title))
            elif action.text() in ("Mouse Mode", "Режим мыши"):
                action.setVisible(False)

    scale_menu = m.addMenu("Масштаб")
    for action, ru_title in axis_actions:
        m.removeAction(action)
        action.setText(ru_title)
        scale_menu.addAction(action)

    # Скрываем стандартный Export pyqtgraph при каждом открытии меню
    def _hide_default_export():
        for action in m.actions():
            txt = action.text().replace("&", "")
            if txt in ("Export...", "Export"):
                action.setVisible(False)
    m.aboutToShow.connect(_hide_default_export)

    # ── ViewBox: форм-виджеты осей (X=ctrl[0], Y=ctrl[1]) ────
    from PyQt6.QtWidgets import QHBoxLayout, QWidget
    _layout_fixed = [False]
    for ui in m.ctrl:
        ui.autoRadio       .setText("Авто")
        ui.manualRadio     .setText("Вручную")
        ui.invertCheck     .setVisible(False)
        ui.mouseCheck      .setVisible(False)
        ui.visibleOnlyCheck.setVisible(False)
        ui.autoPanCheck    .setVisible(False)
        ui.label           .setText("Привязать к:")

    def _resize_axis_ctrls():
        if _layout_fixed[0]:
            return
        _layout_fixed[0] = True

        for ui in m.ctrl:
            pw = ui.autoRadio.parentWidget()
            if pw is None:
                continue

            # Template hardcodes setMaximumSize(200, ...) — remove that limit
            pw.setMaximumWidth(16777215)
            pw.setMinimumWidth(400)

            # Widen the date text fields
            ui.minText.setMinimumWidth(145)
            ui.maxText.setMinimumWidth(145)

            # Put autoRadio + % spin + "Привязать к:" label + combo on one row
            grid = ui.gridLayout
            grid.setContentsMargins(6, 4, 6, 4)
            grid.setSpacing(4)

            grid.removeWidget(ui.autoRadio)
            grid.removeWidget(ui.autoPercentSpin)
            grid.removeWidget(ui.label)
            grid.removeWidget(ui.linkCombo)

            from PyQt6.QtWidgets import QSizePolicy
            ui.linkCombo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            row_w = QWidget(pw)
            hbox  = QHBoxLayout(row_w)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(6)
            hbox.addWidget(ui.autoRadio)
            hbox.addWidget(ui.autoPercentSpin)
            hbox.addSpacing(8)
            hbox.addWidget(ui.label)
            hbox.addWidget(ui.linkCombo, 1)   # stretch=1 → растягивается
            ui.label.setVisible(True)
            ui.linkCombo.setVisible(True)

            grid.addWidget(row_w, 2, 0, 1, 4)
            pw.adjustSize()

            # Tab-advance: Enter в minText → фокус на maxText
            ui.minText.editingFinished.connect(ui.maxText.setFocus)

    m.aboutToShow.connect(_resize_axis_ctrls)

    # ── PlotItem: меню "Plot Options" и его подменю ───────────
    pi = plot_widget.getPlotItem()
    if not (hasattr(pi, "ctrlMenu") and pi.ctrlMenu):
        return

    pi.ctrlMenu.menuAction().setVisible(False)

    _submenu_ru = {
        "Transforms": "Преобразования",
        "Downsample": "Прореживание",
        "Average":    "Усреднение",
        "Alpha":      "Прозрачность",
        "Grid":       "Сетка",
    }
    _hidden = {"Points", "Alpha", "Grid", "Average", "Transforms", "Downsample"}
    for action in pi.ctrlMenu.actions():
        key = action.text().replace("&", "")
        if key in _hidden:
            action.setVisible(False)
            continue
        if key in _submenu_ru:
            if action.menu():
                action.menu().setTitle(_submenu_ru[key])
            else:
                action.setText(_submenu_ru[key])

    # ── PlotItem: форм-виджеты внутри подменю ────────────────
    c = pi.ctrl

    # Transforms
    c.fftCheck         .setText("Спектр мощности (БПФ)")
    c.subtractMeanCheck.setText("Вычесть среднее")
    c.logXCheck        .setText("Лог X")
    c.logYCheck        .setText("Лог Y")
    c.derivativeCheck  .setText("dy/dx")
    c.phasemapCheck    .setText("Y vs. Y'")

    # Downsample
    c.downsampleCheck    .setText("Прореживание")
    c.autoDownsampleCheck.setText("Авто")
    c.subsampleRadio     .setText("Подвыборка")
    c.meanRadio          .setText("Среднее")
    c.peakRadio          .setText("Пик")
    c.clipToViewCheck    .setText("Обрезать по виду")
    c.maxTracesCheck     .setText("Макс. кривых:")
    c.forgetTracesCheck  .setText("Удалять скрытые")

    # Grid
    c.xGridCheck.setText("Сетка X")
    c.yGridCheck.setText("Сетка Y")
    c.label     .setText("Непрозрачность")

    # Alpha
    c.autoAlphaCheck.setText("Авто")

    # Points
    c.autoPointsCheck.setText("Авто")
    c.averageGroup.setTitle("Усреднение")
    c.pointsGroup .setTitle("Точки")
    c.alphaGroup  .setTitle("Прозрачность")

    # ── Экспорт в самом низу меню (скрыт по умолчанию) ──
    sep_action  = m.addSeparator()
    export_menu = m.addMenu("Экспорт")
    csv_action  = QAction("CSV",   export_menu)
    xlsx_action = QAction("Excel", export_menu)
    export_menu.addAction(csv_action)
    export_menu.addAction(xlsx_action)
    export_menu.menuAction().setVisible(False)

    def _keep_at_bottom():
        m.removeAction(sep_action)
        m.removeAction(export_menu.menuAction())
        m.addAction(sep_action)
        m.addAction(export_menu.menuAction())
    m.aboutToShow.connect(_keep_at_bottom)

    return csv_action, xlsx_action, export_menu.menuAction()


def _install_x_time_format(plot_widget):
    """Отображает поля ручного диапазона оси X в формате ЧЧ:ММ:СС.мс"""
    vb   = plot_widget.getViewBox()
    menu = vb.menu

    ctrl_x = menu.ctrl[0] if hasattr(menu, 'ctrl') and menu.ctrl else None
    if ctrl_x is None:
        return
    min_le = ctrl_x.minText
    max_le = ctrl_x.maxText

    def _fmt(ts):
        try:
            dt = _dt.datetime.fromtimestamp(ts)
            return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
        except (OSError, ValueError, OverflowError):
            return f"{ts:g}"

    # Save originals BEFORE shadowing text()
    orig_min_text = min_le.text
    orig_max_text = max_le.text

    def _refresh():
        x0, x1 = vb.viewRange()[0]
        if not min_le.hasFocus():
            min_le.setText(_fmt(x0))
        if not max_le.hasFocus():
            max_le.setText(_fmt(x1))

    # Patch updateState: save user-typed text if field is focused,
    # restore it after _orig_updateState overwrites with "1.7e+09"
    _orig_updateState = menu.updateState
    def _patched_updateState():
        min_focused = min_le.hasFocus()
        max_focused = max_le.hasFocus()
        min_saved = orig_min_text() if min_focused else None
        max_saved = orig_max_text() if max_focused else None

        _orig_updateState()

        x0, x1 = vb.viewRange()[0]
        min_le.setText(min_saved if min_focused else _fmt(x0))
        max_le.setText(max_saved if max_focused else _fmt(x1))

    menu.updateState = _patched_updateState
    menu.aboutToShow.connect(_refresh)

    # Shadow text(): pyqtgraph reads float when applying the range on Enter
    def _parse(orig_fn):
        text = orig_fn()
        try:
            float(text)
            return text
        except ValueError:
            x0, x1 = vb.viewRange()[0]
            ref = _dt.datetime.fromtimestamp((x0 + x1) / 2)
            for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
                try:
                    t = _dt.datetime.strptime(text.strip(), fmt)
                    dt2 = ref.replace(hour=t.hour, minute=t.minute,
                                      second=t.second, microsecond=t.microsecond)
                    return f"{dt2.timestamp():.6f}"
                except ValueError:
                    continue
            return text

    min_le.text = lambda: _parse(orig_min_text)
    max_le.text = lambda: _parse(orig_max_text)
