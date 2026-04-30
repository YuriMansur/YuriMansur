from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QLineEdit, QSpinBox, QComboBox, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QCursor

try:
    import fitz  # PyMuPDF
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False

_DOCS_DIR = Path(__file__).parent.parent / "docs"

_TOOLBAR_STYLE = """
    QPushButton {
        background: #3d5166; color: #ecf0f1;
        border: 1px solid #4a6278; border-radius: 4px;
        padding: 4px 10px; font-size: 12px; min-height: 24px;
    }
    QPushButton:hover   { background: #4a6a82; }
    QPushButton:pressed { background: #2980b9; }
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


class _PageLabel(QLabel):
    """Страница PDF с выделением текста и копированием."""

    text_selected = pyqtSignal(str)

    def __init__(self, page_idx: int, zoom: float, fitz_page, parent=None):
        super().__init__(parent)
        self.page_idx    = page_idx
        self._zoom       = zoom
        self._fitz_page  = fitz_page
        self._origin     = QPoint()
        self._selecting  = False
        self._sel_rect   = QRect()
        self._sel_text   = ""
        self._base_pix   = QPixmap()
        self._search_rects: list[QRect] = []
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_pixmap_base(self, pix: QPixmap):
        self._base_pix = pix
        self._redraw()

    def set_search_rects(self, rects: list):
        self._search_rects = rects
        self._redraw()

    def _redraw(self):
        if self._base_pix.isNull():
            return
        pix = QPixmap(self._base_pix)
        painter = QPainter(pix)
        for r in self._search_rects:
            painter.fillRect(r, QColor(255, 235, 59, 120))
            painter.setPen(QPen(QColor(255, 193, 7), 1))
            painter.drawRect(r)
        if not self._sel_rect.isNull():
            painter.fillRect(self._sel_rect, QColor(52, 152, 219, 100))
            painter.setPen(QPen(QColor(52, 152, 219), 1))
            painter.drawRect(self._sel_rect)
        painter.end()
        self.setPixmap(pix)

    def _rect_to_fitz(self, rect: QRect):
        z = self._zoom
        return fitz.Rect(rect.left() / z, rect.top() / z,
                         rect.right() / z, rect.bottom() / z)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin    = e.pos()
            self._selecting = True
            self._sel_rect  = QRect()
            self._sel_text  = ""
            self._redraw()
        elif e.button() == Qt.MouseButton.RightButton:
            self._sel_rect = QRect()
            self._sel_text = ""
            self._redraw()

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
        self._sel_rect = rect
        if self._fitz_page and _FITZ_OK:
            self._sel_text = self._fitz_page.get_textbox(
                self._rect_to_fitz(rect)
            ).strip()
        self._redraw()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._sel_text:
                QApplication.clipboard().setText(self._sel_text)
                self.text_selected.emit(self._sel_text)
        elif e.key() == Qt.Key.Key_Escape:
            self._sel_rect = QRect()
            self._sel_text = ""
            self._redraw()


class PdfReaderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc     = None
        self._zoom    = 1.5
        self._pages: list[_PageLabel] = []
        self._search_results: list[tuple] = []
        self._search_idx = 0
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

        self.cb_docs = QComboBox()
        self.cb_docs.setFixedWidth(220)
        self.cb_docs.setStyleSheet("""
            QComboBox {
                background: #1a252f; color: #ecf0f1;
                border: 1px solid #4a6278; border-radius: 4px;
                padding: 3px 8px; font-size: 12px; min-height: 24px;
            }
            QComboBox::drop-down { border: none; background: #3d5166; width: 18px; }
            QComboBox QAbstractItemView {
                background: #1a252f; color: #ecf0f1;
                selection-background-color: #1abc9c;
            }
        """)
        self._refresh_docs()

        btn_open = QPushButton("📂 Открыть")
        btn_open.clicked.connect(self._open_selected)

        btn_zoom_out = QPushButton("🔍−")
        btn_zoom_out.clicked.connect(self._zoom_out)
        btn_zoom_in = QPushButton("🔍+")
        btn_zoom_in.clicked.connect(self._zoom_in)

        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(25, 400)
        self.spin_zoom.setValue(int(self._zoom * 100))
        self.spin_zoom.setSuffix("%")
        self.spin_zoom.editingFinished.connect(self._zoom_from_spin)

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

        self.lbl_copied = QLabel("")
        self.lbl_copied.setStyleSheet("color: #1abc9c; font-size: 11px; background: transparent;")

        self.lbl_file = QLabel("Файл не открыт")
        self.lbl_file.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")

        tb_lay.addWidget(self.cb_docs)
        tb_lay.addWidget(btn_open)
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
        tb_lay.addWidget(self.lbl_copied)
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

    def _refresh_docs(self):
        self.cb_docs.clear()
        if _DOCS_DIR.exists():
            for p in sorted(_DOCS_DIR.glob("*.pdf")):
                self.cb_docs.addItem(p.stem, str(p))
        if self.cb_docs.count() == 0:
            self.cb_docs.addItem("— нет файлов —", None)

    def _open_selected(self):
        path = self.cb_docs.currentData()
        if path and _FITZ_OK:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        if not _FITZ_OK:
            return
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(path)
        self.lbl_file.setText(Path(path).name)
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

            lbl = _PageLabel(idx, self._zoom, page)
            lbl.set_pixmap_base(pix)
            lbl.setFixedSize(pix.size())
            lbl.text_selected.connect(self._on_text_selected)

            wrapper = QWidget()
            wrapper.setFixedSize(pix.width() + 8, pix.height() + 8)
            w_lay = QVBoxLayout(wrapper)
            w_lay.setContentsMargins(4, 4, 4, 4)
            w_lay.addWidget(lbl)

            self.pages_layout.addWidget(wrapper, 0, Qt.AlignmentFlag.AlignHCenter)
            self._pages.append(lbl)

        self._highlight_search()

    def _on_text_selected(self, text: str):
        preview = text[:40].replace("\n", " ")
        self.lbl_copied.setText(f"✓ Скопировано: {preview}{'…' if len(text) > 40 else ''}")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.lbl_copied.setText(""))

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
            for r in self._doc[idx].search_for(query):
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
        query = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        for idx, lbl in enumerate(self._pages):
            rects = []
            if query and self._doc:
                for r in self._doc[idx].search_for(query):
                    rects.append(QRect(
                        int(r.x0 * self._zoom), int(r.y0 * self._zoom),
                        int((r.x1 - r.x0) * self._zoom), int((r.y1 - r.y0) * self._zoom),
                    ))
            lbl.set_search_rects(rects)

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
