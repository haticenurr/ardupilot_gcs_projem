"""
mission_panel.py
------------------
Ucus plani (mission) duzenleme paneli.
GCS Yol Haritasi - Ucus Plani ozelligi

Waypoint listesini bir tabloda gosterir, irtifa duzenlemeye izin verir,
gorevi drona yukleme / dosyaya kaydetme / dosyadan yukleme ve endustri
standardi formatlara (.waypoints, .kml) disa aktarma butonlarini icerir.
"""

import json
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView, QDialog
)
from PyQt5.QtCore import pyqtSignal, Qt

from core.exporters import mission_to_kml, mission_to_waypoints
from core.mission_analysis import (
    HATA,
    analyze_mission,
    hata_sayisi,
    mesafe_metni,
    ozet_metni,
)
from ui.pattern_dialog import MOD_ARAMA, MOD_HARITALAMA, PatternDialog


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
        # .waypoints dosyasindaki 0. satir (home) icin; MainWindow
        # HOME_POSITION geldiginde set_home() ile doldurur. Bilinmiyorsa
        # ilk waypoint'in konumu kullanilir.
        self.home = None
        # Gorev analizi icin baglam; MainWindow set_analysis_context() ile
        # gunceller. Bilinmiyorsa analiz yine calisir, sadece eve uzaklik
        # ve geofence kontrolleri atlanir.
        self.fence = {}
        self.cruise_speed_ms = None
        self.mission_mode = "Standart"
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

        self.btn_export = QPushButton("Disa Aktar")
        self.btn_export.setToolTip(
            "Gorevi .waypoints (Mission Planner / QGroundControl) veya "
            ".kml (Google Earth) olarak kaydet"
        )
        self.btn_export.clicked.connect(self.export_mission)
        file_row.addWidget(self.btn_export)
        group_layout.addLayout(file_row)

        self.btn_pattern = QPushButton("OTOMATIK ROTA URET")
        self.btn_pattern.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: 800; padding: 10px;"
        )
        self.btn_pattern.setToolTip(
            "Haritalama: noktalar bir alan tanimlar, icini tarayan rota uretilir.\n"
            "Arama Kurtarma: ilk nokta merkez alinir, genisleyen kare deseni uretilir."
        )
        self.btn_pattern.clicked.connect(self.on_pattern_clicked)
        self.btn_pattern.setVisible(False)  # yalnizca ilgili modlarda gorunur
        group_layout.addWidget(self.btn_pattern)

        self.lbl_analiz = QLabel("Waypoint eklendiginde gorev ozeti burada gorunur.")
        self.lbl_analiz.setWordWrap(True)
        self.lbl_analiz.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; "
            "border-radius: 8px; padding: 8px; color: #a6adc8; font-size: 11px;"
        )
        group_layout.addWidget(self.lbl_analiz)

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
        self._refresh_analysis()

    # ------------------------------------------------------------------
    # Gorev analizi
    # ------------------------------------------------------------------

    def set_analysis_context(self, home=None, fence=None, cruise_speed_ms=None):
        """MainWindow, FC'den ogrendigi home / geofence / seyir hizi
        bilgilerini buraya aktarir. Analiz bunlar olmadan da calisir."""
        if home is not None:
            self.home = home
        if fence is not None:
            self.fence = fence
        if cruise_speed_ms:
            self.cruise_speed_ms = cruise_speed_ms
        self._refresh_analysis()

    def set_mission_mode(self, mode: str):
        """Gorev modu degisince otomatik rota butonunun gorunurlugunu ayarlar."""
        self.mission_mode = mode
        self.btn_pattern.setVisible(mode in (MOD_HARITALAMA, MOD_ARAMA))
        if mode == MOD_HARITALAMA:
            self.btn_pattern.setText("ALANI TARAYAN ROTA URET")
        elif mode == MOD_ARAMA:
            self.btn_pattern.setText("ARAMA DESENI URET")

    def analyze(self):
        """Mevcut gorevin analizini dondurur."""
        return analyze_mission(
            self.waypoints,
            home=self.home,
            speed_ms=self.cruise_speed_ms or 5.0,
            fence=self.fence,
        )

    def _refresh_analysis(self):
        if not self.waypoints:
            self.lbl_analiz.setText(
                "Waypoint eklendiginde gorev ozeti burada gorunur."
            )
            self.lbl_analiz.setStyleSheet(
                "background-color: #181825; border: 1px solid #313244; "
                "border-radius: 8px; padding: 8px; color: #6c7086; font-size: 11px;"
            )
            return

        analiz = self.analyze()
        satirlar = [ozet_metni(analiz)]
        if analiz["eve_en_uzak_m"] is not None:
            satirlar.append(
                f"Eve en uzak: {mesafe_metni(analiz['eve_en_uzak_m'])} · "
                f"donus: {mesafe_metni(analiz['donus_mesafesi_m'])}"
            )
        satirlar.append(
            f"Irtifa: {analiz['min_irtifa_m']:.0f}–{analiz['max_irtifa_m']:.0f} m"
        )

        hatalar = hata_sayisi(analiz)
        uyari_sayisi = len(analiz["uyarilar"]) - hatalar
        if hatalar:
            satirlar.append(f"⚠ {hatalar} guvenlik sorunu — yuklemeden once bakin")
            renk, kenar = "#f38ba8", "#f38ba8"
        elif uyari_sayisi:
            satirlar.append(f"{uyari_sayisi} uyari")
            renk, kenar = "#f9e2af", "#313244"
        else:
            renk, kenar = "#a6e3a1", "#313244"

        self.lbl_analiz.setText("\n".join(satirlar))
        self.lbl_analiz.setStyleSheet(
            f"background-color: #181825; border: 1px solid {kenar}; "
            f"border-radius: 8px; padding: 8px; color: {renk}; font-size: 11px;"
        )

    # ------------------------------------------------------------------
    # Otomatik rota uretimi
    # ------------------------------------------------------------------

    def on_pattern_clicked(self):
        if self.mission_mode not in (MOD_HARITALAMA, MOD_ARAMA):
            return
        gerekli = 3 if self.mission_mode == MOD_HARITALAMA else 1
        if len(self.waypoints) < gerekli:
            QMessageBox.information(
                self,
                "Bilgi",
                f"{self.mission_mode} icin haritaya en az {gerekli} nokta "
                f"ekleyin (su an {len(self.waypoints)}).",
            )
            return

        dialog = PatternDialog(self.mission_mode, self.waypoints, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        uretilen = dialog.get_waypoints()
        if not uretilen:
            return

        self.waypoints = uretilen
        self._refresh_table()
        self.waypoints_changed.emit(self.waypoints)
        self.status_message.emit(
            f"{self.mission_mode} rotasi uretildi: {len(uretilen)} nokta"
        )

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

    def set_home(self, lat, lon):
        """FC'den gelen home konumu; .waypoints disa aktarmasinda 0. satira
        yazilir."""
        self.home = (lat, lon)

    def export_mission(self):
        """Gorevi endustri standardi formatlara aktarir."""
        if not self.waypoints:
            QMessageBox.information(self, "Bilgi", "Disa aktarilacak waypoint yok.")
            return

        wpl_filtre = "Mission Planner Gorevi (*.waypoints)"
        kml_filtre = "Google Earth (*.kml)"
        path, secilen = QFileDialog.getSaveFileName(
            self, "Gorevi Disa Aktar", "gorev.waypoints",
            f"{wpl_filtre};;{kml_filtre}",
        )
        if not path:
            return

        # Bicim once uzantiya, uzanti yoksa secilen filtreye gore belirlenir.
        uzanti = os.path.splitext(path)[1].lower()
        if uzanti == ".kml":
            kml = True
        elif uzanti == ".waypoints":
            kml = False
        else:
            kml = secilen == kml_filtre
            path += ".kml" if kml else ".waypoints"

        try:
            if kml:
                icerik = mission_to_kml(self.waypoints, ad="Ucus Plani")
            else:
                icerik = mission_to_waypoints(self.waypoints, home=self.home)
            with open(path, "w", encoding="utf-8") as f:
                f.write(icerik)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Disa aktarma hatasi: {e}")
            return

        bicim = "KML" if kml else ".waypoints"
        QMessageBox.information(self, "Basarili", f"{bicim} olarak kaydedildi:\n{path}")
        self.status_message.emit(f"Gorev {bicim} olarak disa aktarildi")

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

        # Guvenlik sorunlarini yuklemeden ONCE goster. Geofence disindaki
        # bir waypoint normalde ancak ucus sirasinda failsafe tetiklenince
        # anlasilir.
        analiz = self.analyze()
        hatalar = [u for u in analiz["uyarilar"] if u["seviye"] == HATA]
        if hatalar:
            metin = "\n".join(f"• {u['metin']}" for u in hatalar[:8])
            if len(hatalar) > 8:
                metin += f"\n• ... ve {len(hatalar) - 8} sorun daha"
            cevap = QMessageBox.warning(
                self,
                "Gorevde guvenlik sorunu",
                f"{len(hatalar)} sorun bulundu:\n\n{metin}\n\n"
                f"Yine de yuklemek istiyor musunuz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if cevap != QMessageBox.Yes:
                return

        self.status_message.emit(
            f"Gorev yukleniyor... ({ozet_metni(analiz)})"
        )
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

