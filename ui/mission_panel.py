"""
mission_panel.py
------------------
Ucus plani (mission) duzenleme paneli.
GCS Yol Haritasi - Ucus Plani ozelligi

Waypoint listesini bir tabloda gosterir, irtifa duzenlemeye izin verir,
gorevi drona yukleme / dosyaya kaydetme / dosyadan yukleme butonlarini icerir.
"""

import json

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import pyqtSignal, Qt


DEFAULT_ALTITUDE = 30.0  # metre, yeni eklenen her waypoint icin varsayilan irtifa


class MissionPanel(QWidget):
    waypoints_changed = pyqtSignal(list)   # [(lat, lon, alt), ...]
    upload_requested = pyqtSignal(list)    # main.py bu sinyali worker'a baglar
    download_requested = pyqtSignal()      # drondan gorev readback
    clear_mission_requested = pyqtSignal() # dronun gorev hafizasini sil (mission_clear_all)
    status_message = pyqtSignal(str)       # QStatusBar icin kisa bilgilendirme

    def __init__(self):
        super().__init__()
        self.waypoints = []  # [(lat, lon, alt), ...]
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SetMinimumSize)

        group = QGroupBox("Ucus Plani (Waypoint'ler)")
        group_layout = QVBoxLayout()

        info_label = QLabel("Haritaya tiklayarak waypoint ekleyin. Irtifa hucresine cift tiklayarak degistirebilirsiniz.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        group_layout.addWidget(info_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Enlem (Lat)", "Boylam (Lon)", "Irtifa (m)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self.on_table_item_changed)
        group_layout.addWidget(self.table)

        edit_row = QHBoxLayout()
        self.btn_delete_selected = QPushButton("Secileni Sil")
        self.btn_delete_selected.clicked.connect(self.delete_selected)
        edit_row.addWidget(self.btn_delete_selected)

        self.btn_clear_all = QPushButton("Tumunu Temizle")
        self.btn_clear_all.clicked.connect(self.clear_all)
        edit_row.addWidget(self.btn_clear_all)
        group_layout.addLayout(edit_row)

        self.btn_clear_drone = QPushButton("Gorevi Drondan Sil")
        self.btn_clear_drone.setToolTip(
            "FC'nin gorev hafizasindaki TUM waypoint'leri MISSION_CLEAR_ALL ile siler "
            "ve bu paneldeki listeyi de temizler."
        )
        self.btn_clear_drone.setStyleSheet(
            "background-color: #7f1d1d; color: #fecaca; font-weight: bold; padding: 8px;"
        )
        self.btn_clear_drone.clicked.connect(self.on_clear_drone_clicked)
        group_layout.addWidget(self.btn_clear_drone)

        file_row = QHBoxLayout()
        self.btn_save = QPushButton("Dosyaya Kaydet")
        self.btn_save.clicked.connect(self.save_to_file)
        file_row.addWidget(self.btn_save)

        self.btn_load = QPushButton("Dosyadan Yukle")
        self.btn_load.clicked.connect(self.load_from_file)
        file_row.addWidget(self.btn_load)
        group_layout.addLayout(file_row)

        self.btn_upload = QPushButton("GOREVI DRONA YUKLE")
        self.btn_upload.setStyleSheet(
            "background-color: #2980b9; color: white; font-weight: bold; padding: 10px;"
        )
        self.btn_upload.clicked.connect(self.on_upload_clicked)
        group_layout.addWidget(self.btn_upload)

        self.btn_download = QPushButton("Drondan Gorevi Indir")
        self.btn_download.setStyleSheet(
            "background-color: #1a6b5c; color: #94e2d5; font-weight: bold; padding: 10px;"
        )
        self.btn_download.setToolTip(
            "Yuklenen gorevin FC belleginde dogru kaydedildigini dogrulamak icin readback yapar."
        )
        self.btn_download.clicked.connect(self.on_download_clicked)
        group_layout.addWidget(self.btn_download)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def add_waypoint(self, lat: float, lon: float):
        self.waypoints.append((lat, lon, DEFAULT_ALTITUDE))
        self._refresh_table()
        self.waypoints_changed.emit(self.waypoints)

    def delete_selected(self):
        selected_rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Once tablodan bir satir sec.")
            return
        for row in selected_rows:
            del self.waypoints[row]
        self._refresh_table()
        self.waypoints_changed.emit(self.waypoints)

    def clear_all(self):
        if not self.waypoints:
            return
        reply = QMessageBox.question(
            self, "Onay", "Tum waypoint'ler silinecek, emin misiniz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.waypoints = []
        self._refresh_table()
        self.waypoints_changed.emit(self.waypoints)

    def on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() != 2:
            return
        row = item.row()
        try:
            new_alt = float(item.text())
        except ValueError:
            QMessageBox.warning(self, "Gecersiz deger", "Irtifa bir sayi olmali.")
            self._refresh_table()
            return

        lat, lon, _old_alt = self.waypoints[row]
        self.waypoints[row] = (lat, lon, new_alt)
        self.waypoints_changed.emit(self.waypoints)

    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.waypoints))
        for row, (lat, lon, alt) in enumerate(self.waypoints):
            self.table.setItem(row, 0, QTableWidgetItem(f"{lat:.7f}"))
            self.table.setItem(row, 1, QTableWidgetItem(f"{lon:.7f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{alt:.1f}"))
            self.table.item(row, 0).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.item(row, 1).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.blockSignals(False)

    def save_to_file(self):
        if not self.waypoints:
            QMessageBox.information(self, "Bilgi", "Kaydedilecek waypoint yok.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Ucus Planini Kaydet", "", "JSON Dosyasi (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.waypoints, f, indent=2)
            QMessageBox.information(self, "Basarili", f"Kaydedildi: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kaydetme hatasi: {e}")

    def load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ucus Plani Ac", "", "JSON Dosyasi (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.waypoints = [tuple(wp) for wp in loaded]
            self._refresh_table()
            self.waypoints_changed.emit(self.waypoints)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Yukleme hatasi: {e}")

    def on_upload_clicked(self):
        if not self.waypoints:
            QMessageBox.information(self, "Bilgi", "Once en az bir waypoint ekle.")
            return
        self.status_message.emit("Gorev yukleniyor...")
        self.upload_requested.emit(self.waypoints)

    def on_download_clicked(self):
        self.status_message.emit("Gorev drondan indiriliyor...")
        self.download_requested.emit()

    def on_clear_drone_clicked(self):
        if self.waypoints:
            reply = QMessageBox.question(
                self, "Onay",
                "Dronun hafizasindaki gorev SILINECEK ve bu listedeki tum "
                "waypoint'ler de temizlenecek. Emin misiniz?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self.waypoints = []
        self._refresh_table()
        self.waypoints_changed.emit(self.waypoints)
        self.status_message.emit("Gorev drondan siliniyor...")
        self.clear_mission_requested.emit()

    def set_waypoints(self, waypoints, emit_changed: bool = True):
        """Indirilen veya dosyadan gelen listeyi tabloya yazar."""
        self.waypoints = [tuple(wp) for wp in waypoints]
        self._refresh_table()
        if emit_changed:
            self.waypoints_changed.emit(self.waypoints)

    def show_upload_result(self, success: bool, message: str):
        prefix = "Yuklendi" if success else "Hata"
        self.status_message.emit(f"{prefix}: {message}")
