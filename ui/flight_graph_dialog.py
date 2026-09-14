"""
flight_graph_dialog.py
------------------------
Yuklu bir ucus kaydinin (CSV satirlari) irtifa ve yer hizini zamana gore
gosteren grafik penceresi. matplotlib PyQt5 icine gomulur.
"""

import matplotlib
matplotlib.use("Qt5Agg")

from datetime import datetime

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class FlightGraphDialog(QDialog):
    def __init__(self, rows, filename: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ucus Grafigi - {filename}")
        self.setMinimumSize(720, 480)
        self.setStyleSheet("background-color: #1e1e2e;")

        layout = QVBoxLayout(self)

        title = QLabel(filename)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #89dceb; font-size: 13px; font-weight: 700;")
        layout.addWidget(title)

        elapsed, alt_vals, gs_vals = self._extract_series(rows)

        if not elapsed:
            empty = QLabel("Grafik icin yeterli veri yok.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #6c7086; font-size: 12px;")
            layout.addWidget(empty)
            return

        fig = Figure(figsize=(6, 4), facecolor="#1e1e2e")
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)

        ax_alt = fig.add_subplot(211)
        self._style_axis(ax_alt, "Irtifa (m)")
        ax_alt.plot(elapsed, alt_vals, color="#89dceb", linewidth=1.6)

        ax_gs = fig.add_subplot(212)
        self._style_axis(ax_gs, "Yer Hizi (m/s)")
        ax_gs.set_xlabel("Sure (sn)", color="#a6adc8", fontsize=9)
        ax_gs.plot(elapsed, gs_vals, color="#a6e3a1", linewidth=1.6)

        fig.tight_layout()

    def _extract_series(self, rows):
        elapsed, alt_vals, gs_vals = [], [], []
        t0 = None
        for row in rows:
            try:
                t = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                alt = float(row["alt"])
                gs = float(row["groundspeed"])
            except (ValueError, KeyError):
                continue
            if t0 is None:
                t0 = t
            elapsed.append((t - t0).total_seconds())
            alt_vals.append(alt)
            gs_vals.append(gs)
        return elapsed, alt_vals, gs_vals

    def _style_axis(self, ax, ylabel):
        ax.set_facecolor("#181825")
        ax.set_ylabel(ylabel, color="#a6adc8", fontsize=9)
        ax.tick_params(colors="#6c7086", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#313244")
        ax.grid(True, color="#313244", linewidth=0.5, alpha=0.6)
