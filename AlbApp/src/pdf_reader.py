from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QLineEdit, QToolBar, QFileDialog, QSizePolicy,
    QSlider, QSpinBox, QTextEdit, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QCursor

try:
    import fitz  # PyMuPDF
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False


_TOOLBAR_STYLE = """
    QToolBar {
        background: #2c3e50;
        border-bottom: 1px solid #4a6278;
        spacing: 4px;
        padding: 4px;
    }
    QPushButton {
        background: #3d5166; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 4px;
        padding: 4px 10px; font-size: 12px; min-height: 24px;
    }
    QPushButton:hover   { background: #4a6a82; }
    QPushButton:pressed { background: #2980b9; }
    QPushButton:checked { background: #1abc9c; border-color: #1abc9c; color: #1a252f; }
    QLineEdit {
        background: #1a252f; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 4px;
        padding: 3px 8px; font-size: 12px; min-height: 24px;
    }
    QSpinBox {
        background: #1a252f; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 4px;
        padding: 2px 4px; font-size: 12px; min-width: 52px;
    }
    QLabel { color: #ecf0f1; font-size: 12px; background: transparent; }
"""


class _NoteDialog(QDialog):
    def __init__(self, parent=None, existing=""):
        super().__init__(parent)
        self.setWindowTitle("Заметка")
        self.resize(360, 200)
        lay = QVBoxLayout(self)
        self.edit = QTextEdit()
        self.edit.setPlainText(existing)
        lay.addWidget(self.edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def text(self):
        return self.edit.toPlainText()


class _PageLabel(QLabel):
    """Виджет одной страницы с поддержкой аннотаций."""

    annotation_added = pyqtSignal(int, object)  # page_idx, annot_dict

    def __init__(self, page_idx: int, parent=None):
        super().__init__(parent)
        self.page_idx   = page_idx
        self._tool      = "none"   # "highlight" | "note" | "none"
        self._origin    = QPoint()
        self._selecting = False
        self._sel_rect  = QRect()
        self._base_pix  = QPixmap()
        self._annots: list[dict] = []
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_tool(self, tool: str):
        self._tool = tool
        cur = Qt.CursorShape.IBeamCursor if tool == "highlight" else (
              Qt.CursorShape.CrossCursor if tool == "note" else
              Qt.CursorShape.ArrowCursor)
        self.setCursor(QCursor(cur))

    def set_pixmap_base(self, pix: QPixmap):
        self._base_pix = pix
        self._redraw()

    def add_annotation(self, annot: dict):
        self._annots.append(annot)
        self._redraw()

    def set_annotations(self, annots: list):
        self._annots = list(annots)
        self._redraw()

    def _redraw(self):
        if self._base_pix.isNull():
            return
        pix = QPixmap(self._base_pix)
        painter = QPainter(pix)
        for a in self._annots:
            if a["type"] == "highlight":
                painter.fillRect(a["rect"], QColor(255, 235, 59, 100))
                painter.setPen(QPen(QColor(255, 193, 7), 1))
                painter.drawRect(a["rect"])
            elif a["type"] == "note":
                r = a["rect"]
                painter.setBrush(QColor(255, 235, 59, 180))
                painter.setPen(QPen(QColor(180, 130, 0), 1))
                painter.drawRect(r)
                painter.setPen(QPen(QColor(60, 40, 0)))
                painter.setFont(QFont("Arial", 9))
                painter.drawText(r.adjusted(2, 2, -2, -2),
                                 Qt.TextFlag.TextWordWrap, a.get("text", ""))
        if self._selecting and not self._sel_rect.isNull():
            painter.fillRect(self._sel_rect, QColor(52, 152, 219, 80))
            painter.setPen(QPen(QColor(52, 152, 219), 1, Qt.PenStyle.DashLine))
            painter.drawRect(self._sel_rect)
        painter.end()
        self.setPixmap(pix)

    def mousePressEvent(self, e):
        if self._tool in ("highlight", "note") and e.button() == Qt.MouseButton.LeftButton:
            self._origin    = e.pos()
            self._selecting = True
            self._sel_rect  = QRect()

    def mouseMoveEvent(self, e):
        if self._selecting:
            self._sel_rect = QRect(self._origin, e.pos()).normalized()
            self._redraw()

    def mouseReleaseEvent(self, e):
        if not self._selecting:
            return
        self._selecting = False
        rect = QRect(self._origin, e.pos()).normalized()
        if rect.width() < 4 or rect.height() < 4:
            self._sel_rect = QRect()
            self._redraw()
            return
        self._sel_rect = QRect()

        if self._tool == "highlight":
            annot = {"type": "highlight", "rect": rect}
            self.add_annotation(annot)
            self.annotation_added.emit(self.page_idx, annot)
        elif self._tool == "note":
            dlg = _NoteDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.text().strip():
                annot = {"type": "note", "rect": rect, "text": dlg.text()}
                self.add_annotation(annot)
                self.annotation_added.emit(self.page_idx, annot)


class PdfReaderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc        = None
        self._zoom       = 1.5
        self._pages: list[_PageLabel] = []
        self._annots: dict[int, list] = {}
        self._search_results: list[tuple] = []
        self._search_idx = 0
        self._active_tool = "none"
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: #1a252f;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Тулбар ──────────────────────────────────────────────────────────
        tb = QWidget()
        tb.setStyleSheet(_TOOLBAR_STYLE)
        tb_lay = QHBoxLayout(tb)
        tb_lay.setContentsMargins(6, 4, 6, 4)
        tb_lay.setSpacing(6)

        btn_open = QPushButton("📂 Открыть")
        btn_open.clicked.connect(self._open_file)

        self.btn_highlight = QPushButton("🖍 Выделить")
        self.btn_highlight.setCheckable(True)
        self.btn_highlight.clicked.connect(lambda c: self._set_tool("highlight" if c else "none"))

        self.btn_note = QPushButton("📝 Заметка")
        self.btn_note.setCheckable(True)
        self.btn_note.clicked.connect(lambda c: self._set_tool("note" if c else "none"))

        btn_zoom_out = QPushButton("🔍−")
        btn_zoom_out.clicked.connect(self._zoom_out)
        btn_zoom_in  = QPushButton("🔍+")
        btn_zoom_in.clicked.connect(self._zoom_in)

        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(25, 400)
        self.spin_zoom.setValue(int(self._zoom * 100))
        self.spin_zoom.setSuffix("%")
        self.spin_zoom.editingFinished.connect(self._zoom_from_spin)

        # поиск
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск…")
        self.search_edit.setFixedWidth(180)
        self.search_edit.returnPressed.connect(self._search)
        btn_search = QPushButton("↵")
        btn_search.setFixedWidth(28)
        btn_search.clicked.connect(self._search)
        btn_prev = QPushButton("◀")
        btn_prev.setFixedWidth(28)
        btn_prev.clicked.connect(self._search_prev)
        btn_next = QPushButton("▶")
        btn_next.setFixedWidth(28)
        btn_next.clicked.connect(self._search_next)
        self.lbl_results = QLabel("")

        self.lbl_file = QLabel("Файл не открыт")
        self.lbl_file.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")

        tb_lay.addWidget(btn_open)
        tb_lay.addWidget(self.btn_highlight)
        tb_lay.addWidget(self.btn_note)
        tb_lay.addSpacing(8)
        tb_lay.addWidget(btn_zoom_out)
        tb_lay.addWidget(self.spin_zoom)
        tb_lay.addWidget(btn_zoom_in)
        tb_lay.addSpacing(8)
        tb_lay.addWidget(self.search_edit)
        tb_lay.addWidget(btn_search)
        tb_lay.addWidget(btn_prev)
        tb_lay.addWidget(btn_next)
        tb_lay.addWidget(self.lbl_results)
        tb_lay.addStretch()
        tb_lay.addWidget(self.lbl_file)
        root.addWidget(tb)

        # ── Область страниц ─────────────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: #12202b; }")

        self.pages_container = QWidget()
        self.pages_container.setStyleSheet("background: #12202b;")
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setContentsMargins(20, 20, 20, 20)
        self.pages_layout.setSpacing(12)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.scroll.setWidget(self.pages_container)
        root.addWidget(self.scroll, 1)

        if not _FITZ_OK:
            lbl = QLabel("PyMuPDF не установлен.\nВыполните: pip install pymupdf")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #e74c3c; font-size: 14px; background: transparent;")
            self.pages_layout.addWidget(lbl)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not _FITZ_OK:
            return
        if self._doc:
            self._doc.close()
        self._doc    = fitz.open(path)
        self._annots = {}
        self.lbl_file.setText(path.split("/")[-1].split("\\")[-1])
        self._render_all()

    def _render_all(self):
        for i in reversed(range(self.pages_layout.count())):
            w = self.pages_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._pages.clear()

        if not self._doc:
            return

        mat = fitz.Matrix(self._zoom, self._zoom)
        for idx in range(len(self._doc)):
            page = self._doc[idx]
            clip = page.get_pixmap(matrix=mat, alpha=False)
            img  = QImage(clip.samples, clip.width, clip.height,
                          clip.stride, QImage.Format.Format_RGB888)
            pix  = QPixmap.fromImage(img)

            lbl = _PageLabel(idx)
            lbl.set_pixmap_base(pix)
            lbl.setFixedSize(pix.size())
            lbl.set_tool(self._active_tool)
            lbl.set_annotations(self._annots.get(idx, []))
            lbl.annotation_added.connect(self._on_annotation_added)

            shadow = QLabel()
            shadow.setFixedSize(pix.width() + 8, pix.height() + 8)
            shadow.setStyleSheet("background: #0a1520; border-radius: 3px;")

            wrapper = QWidget()
            wrapper.setFixedSize(pix.width() + 8, pix.height() + 8)
            w_lay = QVBoxLayout(wrapper)
            w_lay.setContentsMargins(4, 4, 4, 4)
            w_lay.addWidget(lbl)

            self.pages_layout.addWidget(wrapper, 0, Qt.AlignmentFlag.AlignHCenter)
            self._pages.append(lbl)

        self._highlight_search()

    def _on_annotation_added(self, page_idx: int, annot: dict):
        self._annots.setdefault(page_idx, []).append(annot)

    def _set_tool(self, tool: str):
        self._active_tool = tool
        if tool != "highlight":
            self.btn_highlight.setChecked(False)
        if tool != "note":
            self.btn_note.setChecked(False)
        for lbl in self._pages:
            lbl.set_tool(tool)

    def _zoom_in(self):
        self._zoom = min(4.0, self._zoom + 0.25)
        self._apply_zoom()

    def _zoom_out(self):
        self._zoom = max(0.25, self._zoom - 0.25)
        self._apply_zoom()

    def _zoom_from_spin(self):
        self._zoom = self.spin_zoom.value() / 100
        self._apply_zoom()

    def _apply_zoom(self):
        self.spin_zoom.setValue(int(self._zoom * 100))
        self._render_all()

    def _search(self):
        if not self._doc or not self.search_edit.text().strip():
            return
        query = self.search_edit.text().strip()
        self._search_results = []
        for idx in range(len(self._doc)):
            hits = self._doc[idx].search_for(query)
            for r in hits:
                self._search_results.append((idx, r))
        self._search_idx = 0
        self._highlight_search()
        self._jump_to_result()
        total = len(self._search_results)
        self.lbl_results.setText(f"{'1' if total else '0'}/{total}")

    def _search_next(self):
        if not self._search_results:
            return
        self._search_idx = (self._search_idx + 1) % len(self._search_results)
        self._jump_to_result()
        self.lbl_results.setText(f"{self._search_idx + 1}/{len(self._search_results)}")

    def _search_prev(self):
        if not self._search_results:
            return
        self._search_idx = (self._search_idx - 1) % len(self._search_results)
        self._jump_to_result()
        self.lbl_results.setText(f"{self._search_idx + 1}/{len(self._search_results)}")

    def _highlight_search(self):
        if not self._pages:
            return
        query = self.search_edit.text().strip()
        for idx, lbl in enumerate(self._pages):
            extra = []
            if query and self._doc:
                hits = self._doc[idx].search_for(query)
                for r in hits:
                    rect = QRect(
                        int(r.x0 * self._zoom), int(r.y0 * self._zoom),
                        int((r.x1 - r.x0) * self._zoom), int((r.y1 - r.y0) * self._zoom),
                    )
                    extra.append({"type": "highlight", "rect": rect})
            lbl.set_annotations(self._annots.get(idx, []) + extra)

    def _jump_to_result(self):
        if not self._search_results or self._search_idx >= len(self._search_results):
            return
        page_idx, _ = self._search_results[self._search_idx]
        if page_idx < len(self._pages):
            self.scroll.ensureWidgetVisible(self._pages[page_idx])


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = PdfReaderWidget()
    w.resize(1000, 800)
    w.show()
    sys.exit(app.exec())
