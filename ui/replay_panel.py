"""
replay_panel.py
-----------------
Kayitli ucus loglarini (CSV) haritada ve telemetri kartlarinda geriye donuk oynatir.
"""

import os
import csv
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSlider,
    QFrame,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
from ui.flight_graph_dialog import FlightGraphDialog


class ReplayPanel(QWidget):
    sample_ready = pyqtSignal(dict)  # tek bir CSV satirini GUI'ye iletir
    state_changed = pyqtSignal(bool)  # True: oynatiliyor, False: durduruldu/bitti
    clear_requested = pyqtSignal()  # haritadaki rotayi temizleme istegi

    def __init__(self, log_dir="logs"):
        super().__init__()
        self.log_dir = log_dir
        self.rows = []
        self.current_index = 0
        self.playback_speed = 1.0

        self.timer = QTimer()
        self.timer.timeout.connect(self._advance)

        self.setObjectName("replayPanel")
        self.setStyleSheet(
            """
            QWidget#replayPanel {
                background-color: #181825;
            }
            QFrame#replayStrip, QFrame#replayTransport {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 10px;
            }
            QPushButton#replayIconBtn {
                background-color: #313244;
                color: #cdd6f4;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
                padding: 0px;
                min-width: 40px;
                min-height: 40px;
            }
            QPushButton#replayIconBtn:hover {
                background-color: #45475a;
                color: #89dceb;
            }
            QPushButton#replayIconBtn:pressed {
                background-color: #585b70;
            }
            QPushButton#replayIconBtn:disabled {
                background-color: #313244;
                color: #6c7086;
            }
            QPushButton#replayPlayBtn {
                background-color: #89dceb;
                color: #1e1e2e;
                border: none;
                border-radius: 22px;
                font-size: 18px;
                font-weight: 800;
                padding: 0px;
                min-width: 44px;
                min-height: 44px;
            }
            QPushButton#replayPlayBtn:hover {
                background-color: #a6e3a1;
            }
            QPushButton#replayPlayBtn:disabled {
                background-color: #313244;
                color: #6c7086;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #89dceb;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #a6e3a1;
                border-radius: 3px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        strip = QFrame()
        strip.setObjectName("replayStrip")
        strip_row = QHBoxLayout(strip)
        strip_row.setContentsMargins(10, 8, 10, 8)
        strip_row.setSpacing(8)

        self.file_combo = QComboBox()
        self.file_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.file_combo.setMinimumWidth(160)
        self.file_combo.setToolTip("Kayit dosyasi")
        strip_row.addWidget(self.file_combo, 1)

        self.meta_label = QLabel("—")
        self.meta_label.setStyleSheet(
            "color: #a6adc8; font-size: 12px; font-weight: 600; padding: 0 6px;"
        )
        self.meta_label.setMinimumWidth(180)
        strip_row.addWidget(self.meta_label, 0)

        self.refresh_button = self._icon_button("↻", "Dosya listesini yenile")
        self.refresh_button.clicked.connect(self.refresh_file_list)
        strip_row.addWidget(self.refresh_button)

        self.load_button = self._icon_button("⬇", "Kaydi yukle")
        self.load_button.clicked.connect(self.load_selected_file)
        strip_row.addWidget(self.load_button)
        layout.addWidget(strip)

        self.info_label = QLabel("Kayit yuklenmedi.")
        self.info_label.setStyleSheet("color: #6c7086; font-size: 11px; padding-left: 4px;")
        layout.addWidget(self.info_label)

        transport = QFrame()
        transport.setObjectName("replayTransport")
        controls_row = QHBoxLayout(transport)
        controls_row.setContentsMargins(12, 10, 12, 10)
        controls_row.setSpacing(8)
        controls_row.addStretch(1)

        self.stop_button = self._icon_button("⏮", "Basa sar")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.reset_playback)
        controls_row.addWidget(self.stop_button)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("replayPlayBtn")
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.setFixedSize(44, 44)
        self.play_button.setEnabled(False)
        self.play_button.setToolTip("Oynat")
        self.play_button.clicked.connect(self.toggle_play)
        controls_row.addWidget(self.play_button)

        self.clear_button = self._icon_button("⌫", "Rotayi temizle")
        self.clear_button.clicked.connect(self.clear_requested.emit)
        controls_row.addWidget(self.clear_button)
        
        self.graph_button = self._icon_button("📈", "Ucus grafigini goster")
        self.graph_button.setEnabled(False)
        self.graph_button.clicked.connect(self.show_graph)
        controls_row.addWidget(self.graph_button)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1x", "2x", "5x", "10x"])
        self.speed_combo.setFixedWidth(72)
        self.speed_combo.setToolTip("Oynatma hizi")
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        controls_row.addWidget(self.speed_combo)

        controls_row.addStretch(1)
        layout.addWidget(transport)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.setToolTip("Zaman")
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.valueChanged.connect(self._on_slider_moved)
        layout.addWidget(self.slider)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet(
            "color: #89dceb; font-size: 28px; font-weight: 800; letter-spacing: 1px;"
        )
        layout.addWidget(self.time_label)

        layout.addStretch(1)

        self.refresh_file_list()

    def _icon_button(self, glyph: str, tooltip: str) -> QPushButton:
        btn = QPushButton(glyph)
        btn.setObjectName("replayIconBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(40, 40)
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip(tooltip)
        return btn

    def _set_playing_visual(self, playing: bool):
        if playing:
            self.play_button.setText("⏸")
            self.play_button.setToolTip("Duraklat")
        else:
            self.play_button.setText("▶")
            self.play_button.setToolTip("Oynat")

    def refresh_file_list(self):
        self.file_combo.clear()
        if not os.path.isdir(self.log_dir):
            return
        files = sorted(
            [f for f in os.listdir(self.log_dir) if f.endswith(".csv")],
            reverse=True,
        )
        self.file_combo.addItems(files)

    def load_selected_file(self):
        filename = self.file_combo.currentText()
        if not filename:
            self.info_label.setText("Once bir kayit dosyasi sec.")
            return
        filepath = os.path.join(self.log_dir, filename)
        try:
            with open(filepath, newline="") as f:
                reader = csv.DictReader(f)
                self.rows = list(reader)
        except Exception as e:
            self.info_label.setText(f"Dosya okunamadi: {e}")
            return

        if not self.rows:
            self.info_label.setText("Kayit dosyasi bos.")
            return

        self.current_index = 0
        self.slider.setEnabled(True)
        self.slider.setMinimum(0)
        self.slider.setMaximum(len(self.rows) - 1)
        self.slider.setValue(0)
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.graph_button.setEnabled(True)
        self._set_playing_visual(False)
        self.info_label.setText(f"{len(self.rows)} satir yuklendi: {filename}")
        self._update_file_meta(filename)
        self.clear_requested.emit()
        self._emit_row(0)
        self._update_time_label()

    def _update_file_meta(self, filename: str):
        stamp = "—"
        duration = "00:00"
        try:
            t0 = datetime.strptime(self.rows[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
            t_end = datetime.strptime(self.rows[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
            stamp = t0.strftime("%Y-%m-%d %H:%M")
            total = int((t_end - t0).total_seconds())
            duration = f"{total // 60:02d}:{total % 60:02d}"
        except Exception:
            pass
        self.meta_label.setText(f"{stamp}  ·  {duration}")
        self.meta_label.setToolTip(filename)

    def toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self._set_playing_visual(False)
            self.state_changed.emit(False)
        else:
            if self.current_index >= len(self.rows) - 1:
                self.current_index = 0
            self._schedule_next()
            self._set_playing_visual(True)
            self.state_changed.emit(True)

    def reset_playback(self):
        self.timer.stop()
        self._set_playing_visual(False)
        self.state_changed.emit(False)
        self.current_index = 0
        if self.rows:
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
            self._emit_row(0)
            self._update_time_label()

    def _schedule_next(self):
        if self.current_index >= len(self.rows) - 1:
            self.timer.stop()
            self._set_playing_visual(False)
            self.state_changed.emit(False)
            return
        row_a = self.rows[self.current_index]
        row_b = self.rows[self.current_index + 1]
        try:
            t_a = datetime.strptime(row_a["timestamp"], "%Y-%m-%d %H:%M:%S")
            t_b = datetime.strptime(row_b["timestamp"], "%Y-%m-%d %H:%M:%S")
            delta_ms = max(50, min((t_b - t_a).total_seconds() * 1000, 1500))
        except Exception:
            delta_ms = 200
        interval = max(20, int(delta_ms / self.playback_speed))
        self.timer.start(interval)

    def _advance(self):
        self.timer.stop()
        self.current_index += 1
        if self.current_index >= len(self.rows):
            self.current_index = len(self.rows) - 1
            self._set_playing_visual(False)
            self.state_changed.emit(False)
            return
        self.slider.blockSignals(True)
        self.slider.setValue(self.current_index)
        self.slider.blockSignals(False)
        self._emit_row(self.current_index)
        self._update_time_label()
        self._schedule_next()

    def _on_slider_pressed(self):
        self.timer.stop()
        self._set_playing_visual(False)
        self.state_changed.emit(False)

    def _on_slider_moved(self, value):
        if not self.rows:
            return
        self.current_index = value
        self._emit_row(value)
        self._update_time_label()

    def _on_speed_changed(self, text):
        try:
            self.playback_speed = float(text.replace("x", ""))
        except ValueError:
            self.playback_speed = 1.0

    def _emit_row(self, index):
        row = self.rows[index]
        try:
            data = {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "alt": float(row["alt"]),
                "groundspeed": float(row["groundspeed"]),
                "heading": float(row["heading"]),
                "battery": row["battery"],
                "mode": row["mode"],
                "armed": row["armed"],
                "timestamp": row["timestamp"],
            }
        except (ValueError, KeyError):
            return
        self.sample_ready.emit(data)

    def _update_time_label(self):
        if not self.rows:
            self.time_label.setText("00:00 / 00:00")
            return
        try:
            t0 = datetime.strptime(self.rows[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
            t_now = datetime.strptime(self.rows[self.current_index]["timestamp"], "%Y-%m-%d %H:%M:%S")
            t_end = datetime.strptime(self.rows[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
            elapsed = int((t_now - t0).total_seconds())
            total = int((t_end - t0).total_seconds())
            self.time_label.setText(
                f"{elapsed // 60:02d}:{elapsed % 60:02d} / {total // 60:02d}:{total % 60:02d}"
            )
        except Exception:
            pass
            
    def show_graph(self):
        if not self.rows:
            return
        filename = self.file_combo.currentText() or "Ucus Kaydi"
        dialog = FlightGraphDialog(self.rows, filename, parent=self)
        dialog.exec_()
