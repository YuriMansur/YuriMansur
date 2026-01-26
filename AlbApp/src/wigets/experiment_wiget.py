from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt       
        
class ExperimentWidget(QWidget):
    def __init__(self):
        super().__init__()
        page1_layout = QVBoxLayout(self) #
        # Заголовок с подсветкой
        label1 = QLabel("Испытание")
        label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label1.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1abc9c;
                padding: 20px;
                background-color: rgba(26, 188, 156, 0.1);
            }
        """)
        # Добавление заголовка в layout
        page1_layout.addWidget(label1)