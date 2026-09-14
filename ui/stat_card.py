"""
stat_card.py
-------------
Modern "dashboard" gorunumu icin kart bileseni.
Buyuk, renkli sayilar + kucuk baslik/birim - Mission Planner'in duz
etiket listesinden cok daha goze carpan bir telemetri gosterimi saglar.
"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt


class StatCard(QFrame):
    def __init__(self, title: str, unit: str = "", accent: str = "#3b82f6"):
        super().__init__()
        self.setObjectName("statCard")
        self.setMinimumHeight(108)
        self.setStyleSheet("""
            QFrame#statCard {
                background-color: #1e1e2e;
                border-radius: 14px;
                border: 1px solid #313244;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        self.title_label = QLabel(title.upper())
        self.title_label.setStyleSheet(
            "color: #a6adc8; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; border: none; background: transparent;"
        )
        layout.addWidget(self.title_label)

        value_row = QHBoxLayout()
        value_row.setSpacing(4)

        self.value_label = QLabel("--")
        self.value_label.setStyleSheet(
            f"color: {accent}; font-size: 32px; font-weight: 800; border: none; background: transparent;"
        )
        value_row.addWidget(self.value_label)

        self.unit_label = QLabel(unit)
        self.unit_label.setStyleSheet(
            "color: #6c7086; font-size: 12px; font-weight: 600; border: none; background: transparent; padding-bottom: 6px;"
        )
        self.unit_label.setAlignment(Qt.AlignBottom)
        value_row.addWidget(self.unit_label)
        value_row.addStretch()

        layout.addLayout(value_row)

    def set_value(self, text):
        self.value_label.setText(str(text))

    def set_accent(self, color: str):
        self.value_label.setStyleSheet(
            f"color: {color}; font-size: 32px; font-weight: 800; border: none; background: transparent;"
        )


def make_badge(text: str, bg_color: str, fg_color: str = "white") -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"""
        QLabel {{
            background-color: {bg_color};
            color: {fg_color};
            font-size: 11px;
            font-weight: 700;
            padding: 5px 12px;
            border-radius: 10px;
        }}
    """)
    return label
