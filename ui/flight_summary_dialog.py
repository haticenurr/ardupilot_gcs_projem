"""
flight_summary_dialog.py
--------------------------
Biten ucusun kapsamli ozetini gosteren rapor penceresi. DISARM aninda
KENDILIGINDEN ACILMAZ; MainWindow ozeti saklar ve pilot 'SON UCUS OZETI'
butonuna bastiginda bu pencere acilir. Kullanici raporu .txt dosyasi
olarak da kaydedebilir.
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QFileDialog
)
from PyQt5.QtCore import Qt


class _StatBox(QFrame):
    def __init__(self, title: str, value: str, color: str, span_note: str = ""):
        super().__init__()
        self.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; border-radius: 10px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #a6adc8; font-size: 10px; font-weight: 700;")
        layout.addWidget(title_lbl)

        value_lbl = QLabel(value)
        value_lbl.setWordWrap(True)
        value_lbl.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: 800;")
        layout.addWidget(value_lbl)

        if span_note:
            note_lbl = QLabel(span_note)
            note_lbl.setStyleSheet("color: #6c7086; font-size: 9px; font-weight: 600;")
            layout.addWidget(note_lbl)


class FlightSummaryDialog(QDialog):
    def __init__(self, duration_s: float, max_alt: float, max_speed: float,
                 distance_m: float, min_battery, min_satellites, mode_changes: int,
                 fence_breach: bool, start_iso, flight_name: str, log_filename,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ucus Ozeti")
        self.setMinimumWidth(460)
        self.setStyleSheet("background-color: #1e1e2e;")

        self._duration_s = duration_s
        self._max_alt = max_alt
        self._max_speed = max_speed
        self._distance_m = distance_m
        self._min_battery = min_battery
        self._min_satellites = min_satellites
        self._mode_changes = mode_changes
        self._fence_breach = fence_breach
        self._start_iso = start_iso
        self._flight_name = flight_name
        self._log_filename = log_filename

        layout = QVBoxLayout(self)

        title = QLabel(f"Ucus Tamamlandi{': ' + flight_name if flight_name else ''}")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("color: #89dceb; font-size: 14px; font-weight: 800;")
        layout.addWidget(title)

        if start_iso:
            date_lbl = QLabel(start_iso)
            date_lbl.setAlignment(Qt.AlignCenter)
            date_lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: 600;")
            layout.addWidget(date_lbl)

        minutes, seconds = divmod(int(duration_s), 60)
        battery_text = f"%{int(min_battery)}" if min_battery is not None and min_battery >= 0 else "--"
        sat_text = str(min_satellites) if min_satellites is not None else "--"
        avg_speed = (distance_m / duration_s) if duration_s > 0 else 0.0
        fence_text = "IHLAL EDILDI" if fence_breach else "Ihlal yok"
        fence_color = "#f38ba8" if fence_breach else "#a6e3a1"

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.addWidget(_StatBox("SURE", f"{minutes:02d}:{seconds:02d}", "#89dceb"), 0, 0)
        grid.addWidget(_StatBox("MAKS IRTIFA", f"{max_alt:.1f} m", "#94e2d5"), 0, 1)
        grid.addWidget(_StatBox("MAKS HIZ", f"{max_speed:.1f} m/s", "#89b4fa"), 1, 0)
        grid.addWidget(_StatBox("ORT. HIZ", f"{avg_speed:.1f} m/s", "#89b4fa"), 1, 1)
        grid.addWidget(_StatBox("MESAFE", f"{distance_m:.0f} m", "#fab387"), 2, 0)
        grid.addWidget(_StatBox("MIN PIL", battery_text, "#a6e3a1"), 2, 1)
        grid.addWidget(_StatBox("MIN GPS UYDU", sat_text, "#cba6f7"), 3, 0)
        grid.addWidget(_StatBox("MOD DEGISIMI", str(mode_changes), "#f9e2af"), 3, 1)
        grid.addWidget(_StatBox("GEOFENCE DURUMU", fence_text, fence_color), 4, 0, 1, 2)
        layout.addLayout(grid)

        if log_filename:
            file_lbl = QLabel(f"Kayit dosyasi: {log_filename}")
            file_lbl.setStyleSheet("color: #6c7086; font-size: 10px; margin-top: 6px;")
            file_lbl.setWordWrap(True)
            layout.addWidget(file_lbl)

        save_btn = QPushButton("Raporu Kaydet (.txt)")
        save_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; "
            "padding: 9px; border-radius: 8px; margin-top: 10px;"
        )
        save_btn.clicked.connect(self._on_save_clicked)
        layout.addWidget(save_btn)

        close_btn = QPushButton("Kapat")
        close_btn.setStyleSheet(
            "background-color: #313244; color: #cdd6f4; font-weight: 700; "
            "padding: 8px; border-radius: 8px; margin-top: 4px;"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _build_report_text(self) -> str:
        minutes, seconds = divmod(int(self._duration_s), 60)
        battery_text = (
            f"%{int(self._min_battery)}"
            if self._min_battery is not None and self._min_battery >= 0
            else "Bilinmiyor"
        )
        sat_text = str(self._min_satellites) if self._min_satellites is not None else "Bilinmiyor"
        avg_speed = (self._distance_m / self._duration_s) if self._duration_s > 0 else 0.0
        fence_text = "IHLAL EDILDI" if self._fence_breach else "Ihlal yok"

        lines = [
            "=" * 40,
            "UCUS OZET RAPORU",
            "=" * 40,
            f"Ucus Adi: {self._flight_name or '(isimsiz)'}",
            f"Tarih/Saat: {self._start_iso or 'Bilinmiyor'}",
            f"Kayit Dosyasi: {self._log_filename or 'Bilinmiyor'}",
            "-" * 40,
            f"Sure: {minutes:02d}:{seconds:02d}",
            f"Maksimum Irtifa: {self._max_alt:.1f} m",
            f"Maksimum Hiz: {self._max_speed:.1f} m/s",
            f"Ortalama Hiz: {avg_speed:.1f} m/s",
            f"Kat Edilen Mesafe: {self._distance_m:.0f} m",
            f"Minimum Batarya: {battery_text}",
            f"Minimum GPS Uydu Sayisi: {sat_text}",
            f"Ucus Modu Degisim Sayisi: {self._mode_changes}",
            f"Geofence Durumu: {fence_text}",
            "=" * 40,
            f"Rapor olusturma: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        return "\n".join(lines)

    def _on_save_clicked(self):
        default_name = (self._flight_name or "ucus_ozeti").replace(" ", "_") + "_rapor.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Raporu Kaydet", default_name, "Metin Dosyasi (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._build_report_text())
        except Exception as e:
            error_lbl = QLabel(f"Kaydedilemedi: {e}")
            error_lbl.setStyleSheet("color: #f38ba8; font-size: 10px;")
            self.layout().addWidget(error_lbl)
