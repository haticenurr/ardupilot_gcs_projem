"""
preflight_checklist_dialog.py
-------------------------------
ARM'dan once acilabilen, o anki kritik ucus-oncesi durumlari tek bir
listede ozetleyen kontrol sihirbazi. Salt bilgilendirme amaclidir;
gercek ARM islemini gerceklestirmez, sadece pilotu bilgilendirir.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt5.QtCore import Qt


def _dot_style(color: str) -> str:
    return f"background-color: {color}; border-radius: 6px;"


class ChecklistRow(QFrame):
    """Tek bir kontrol satiri: nokta + baslik + detay metni."""

    def __init__(self, title: str, status, detail: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        dot = QLabel()
        dot.setFixedSize(12, 12)
        if status is True:
            dot.setStyleSheet(_dot_style("#a6e3a1"))
        elif status is False:
            dot.setStyleSheet(_dot_style("#f38ba8"))
        else:
            dot.setStyleSheet(_dot_style("#6c7086"))
        layout.addWidget(dot)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #cdd6f4; font-weight: 700; font-size: 12px;")
        layout.addWidget(title_lbl)
        layout.addStretch()

        detail_lbl = QLabel(detail)
        detail_lbl.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: 600;")
        layout.addWidget(detail_lbl)


class PreflightChecklistDialog(QDialog):
    def __init__(self, checks: list, all_required_ok: bool, parent=None):
        """
        checks: [(title, status, detail, required_bool), ...]
          status: True/False/None
          required_bool: bu madde genel "ARM'a hazir" kararina dahil mi
        """
        super().__init__(parent)
        self.setWindowTitle("Ucus Oncesi Kontrol Listesi")
        self.setMinimumWidth(420)
        self.setStyleSheet("background-color: #1e1e2e;")

        layout = QVBoxLayout(self)

        title = QLabel("Ucus Oncesi Kontrol Listesi")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #89dceb; font-size: 14px; font-weight: 800;")
        layout.addWidget(title)

        banner = QLabel("ARM'A HAZIR" if all_required_ok else "ARM'A HAZIR DEGIL")
        banner.setAlignment(Qt.AlignCenter)
        bg = "#a6e3a1" if all_required_ok else "#f38ba8"
        banner.setStyleSheet(
            f"background-color: {bg}; color: #1e1e2e; font-weight: 800; "
            f"font-size: 13px; padding: 10px; border-radius: 8px; margin: 6px 0;"
        )
        layout.addWidget(banner)

        for title_text, status, detail, required in checks:
            row = ChecklistRow(title_text, status, detail)
            layout.addWidget(row)

        note = QLabel(
            "Not: Geofence ve Gorev Yuklu maddeleri bilgi amaclidir, "
            "ARM'a hazir olma kararini etkilemez."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c7086; font-size: 10px; margin-top: 6px;")
        layout.addWidget(note)

        close_btn = QPushButton("Kapat")
        close_btn.setStyleSheet(
            "background-color: #313244; color: #cdd6f4; font-weight: 700; "
            "padding: 8px; border-radius: 8px; margin-top: 8px;"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
