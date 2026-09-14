"""
event_log_panel.py
-------------------
Kalici Olay Gunlugu (Event Log) paneli.
Durum cubugunda gosterilen mesajlar birkac saniyede kayboluyordu;
bu panel ayni mesajlari zaman damgasiyla kalici olarak listeler.
"""

from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class EventLogPanel(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.clear_button = QPushButton("Gunlugu Temizle")
        self.clear_button.clicked.connect(self.clear_log)
        button_row.addWidget(self.clear_button)
        layout.addLayout(button_row)

    def add_event(self, message: str, success=None):
        """success: True (basarili/yesil), False (hata/kirmizi), None (notr/gri)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{timestamp}] {message}")

        if success is True:
            item.setForeground(QColor("#a6e3a1"))
        elif success is False:
            item.setForeground(QColor("#f38ba8"))
        else:
            item.setForeground(QColor("#cdd6f4"))

        self.list_widget.addItem(item)
        self.list_widget.scrollToBottom()

    def clear_log(self):
        self.list_widget.clear()
