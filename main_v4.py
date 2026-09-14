import sys
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QGroupBox, QPushButton, QComboBox, QMessageBox, QSplitter,
    QTabWidget
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from map_widget_v2 import DroneMapWidget
from mission_panel import MissionPanel


class TelemetryWorker(QThread):
    telemetry_signal = pyqtSignal(dict)
    connection_status_signal = pyqtSignal(bool, str)
    mission_upload_result = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.drone = None
        self.paused_for_mission = False

    def run(self):
        try:
            from drone_telemetry import DroneTelemetry
            self.drone = DroneTelemetry()
            self.connection_status_signal.emit(True, "Baglanti basarili")
        except Exception as e:
            print(f"Bağlantı başlatılamadı: {e}")
            self.connection_status_signal.emit(False, str(e))
            return

        while self.is_running:
            if self.paused_for_mission:
                time.sleep(0.05)
                continue
            try:
                if self.drone:
                    data = self.drone.get_telemetry_data()
                    if data:
                        self.telemetry_signal.emit(data)
            except Exception:
                pass
            time.sleep(0.05)

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()

    def arm_disarm(self, arm: bool):
        if self.drone:
            try:
                self.drone.send_arm_disarm(arm)
            except Exception as e:
                print(f"Arm/Disarm hatasi: {e}")

    def change_mode(self, mode_name: str):
        if self.drone:
            try:
                self.drone.set_mode(mode_name)
            except Exception as e:
                print(f"Mod degistirme hatasi: {e}")

    def upload_mission(self, waypoints):
        if not self.drone:
            self.mission_upload_result.emit(False, "Baglanti yok")
            return

        self.paused_for_mission = True
        try:
            success, message = self.drone.upload_mission(waypoints)
        except Exception as e:
            success, message = False, f"Beklenmeyen hata: {e}"
        finally:
            self.paused_for_mission = False

        self.mission_upload_result.emit(success, message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GCS Ana Ekran - Drone Telemetri ve Ucus Plani")
        self.resize(1000, 650)

        self.is_armed = False

        self.setup_ui()

        print("Ağ dinleme işlemi arka planda başlatılıyor...")
        self.worker = TelemetryWorker()
        self.worker.telemetry_signal.connect(self.update_telemetry_ui)
        self.worker.connection_status_signal.connect(self.update_connection_status)
        self.worker.mission_upload_result.connect(self.mission_panel.show_upload_result)
        self.worker.start()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        outer_layout = QHBoxLayout(central_widget)

        tabs = QTabWidget()

        telemetry_tab = QWidget()
        telemetry_layout = QVBoxLayout(telemetry_tab)

        self.lbl_status = QLabel("Baglanti durumu: Bekleniyor...")
        self.lbl_status.setStyleSheet("font-weight: bold;")
        telemetry_layout.addWidget(self.lbl_status)

        attitude_group = QGroupBox("Yönelim (Attitude)")
        attitude_layout = QVBoxLayout()
        self.lbl_pitch = QLabel("Pitch: Bekleniyor...")
        self.lbl_roll = QLabel("Roll: Bekleniyor...")
        self.lbl_yaw = QLabel("Yaw: Bekleniyor...")
        font = self.lbl_pitch.font()
        font.setPointSize(11)
        for lbl in [self.lbl_pitch, self.lbl_roll, self.lbl_yaw]:
            lbl.setFont(font)
            attitude_layout.addWidget(lbl)
        attitude_group.setLayout(attitude_layout)
        telemetry_layout.addWidget(attitude_group)

        position_group = QGroupBox("Küresel Konum (Global Position)")
        position_layout = QVBoxLayout()
        self.lbl_lat = QLabel("Enlem (Lat): Bekleniyor...")
        self.lbl_lon = QLabel("Boylam (Lon): Bekleniyor...")
        self.lbl_alt = QLabel("İrtifa (Alt): Bekleniyor...")
        for lbl in [self.lbl_lat, self.lbl_lon, self.lbl_alt]:
            lbl.setFont(font)
            position_layout.addWidget(lbl)
        position_group.setLayout(position_layout)
        telemetry_layout.addWidget(position_group)

        control_group = QGroupBox("Komuta ve Kontrol")
        control_layout = QVBoxLayout()
        self.btn_arm = QPushButton("ARM (Motorlari Kilitle Ac)")
        self.btn_arm.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 8px;")
        self.btn_arm.clicked.connect(self.on_arm_disarm_clicked)
        control_layout.addWidget(self.btn_arm)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Ucus Modu:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["STABILIZE", "GUIDED", "AUTO", "RTL", "LAND", "LOITER"])
        mode_row.addWidget(self.mode_combo)
        self.btn_set_mode = QPushButton("Uygula")
        self.btn_set_mode.clicked.connect(self.on_set_mode_clicked)
        mode_row.addWidget(self.btn_set_mode)
        control_layout.addLayout(mode_row)
        control_group.setLayout(control_layout)
        telemetry_layout.addWidget(control_group)

        telemetry_layout.addStretch()
        tabs.addTab(telemetry_tab, "Telemetri ve Kontrol")

        self.mission_panel = MissionPanel()
        self.mission_panel.waypoints_changed.connect(self.on_waypoints_changed)
        self.mission_panel.upload_requested.connect(self.on_mission_upload_requested)
        tabs.addTab(self.mission_panel, "Uçuş Planı")

        tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs = tabs

        self.map_widget = DroneMapWidget()
        self.map_widget.waypoint_added.connect(self.mission_panel.add_waypoint)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(tabs)
        splitter.addWidget(self.map_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 640])

        outer_layout.addWidget(splitter)

        self.map_widget.set_mission_editing(False)

    def on_tab_changed(self, index):
        tab_text = self.tabs.tabText(index)
        self.map_widget.set_mission_editing(tab_text == "Uçuş Planı")

    def on_waypoints_changed(self, waypoints):
        self.map_widget.redraw_waypoints(waypoints)

    def on_mission_upload_requested(self, waypoints):
        self.worker.upload_mission(waypoints)

    def update_connection_status(self, success: bool, message: str):
        if success:
            self.lbl_status.setText("Baglanti durumu: BAGLANDI")
            self.lbl_status.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.lbl_status.setText(f"Baglanti durumu: HATA ({message})")
            self.lbl_status.setStyleSheet("font-weight: bold; color: red;")

    def update_telemetry_ui(self, data):
        msg_type = data.get('type')
        if msg_type == 'ATTITUDE':
            self.lbl_pitch.setText(f"Pitch: {data['pitch']:.3f} rad")
            self.lbl_roll.setText(f"Roll: {data['roll']:.3f} rad")
            self.lbl_yaw.setText(f"Yaw: {data['yaw']:.3f} rad")
        elif msg_type == 'GLOBAL_POSITION_INT':
            self.lbl_lat.setText(f"Enlem (Lat): {data['lat']:.6f}°")
            self.lbl_lon.setText(f"Boylam (Lon): {data['lon']:.6f}°")
            self.lbl_alt.setText(f"İrtifa (Alt): {data['alt']:.2f} m")
            self.map_widget.update_position(data['lat'], data['lon'])

    def on_arm_disarm_clicked(self):
        action_text = "DISARM" if self.is_armed else "ARM"
        reply = QMessageBox.question(
            self, "Onay",
            f"Drone'u {action_text} etmek istediginizden emin misiniz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.is_armed = not self.is_armed
        self.worker.arm_disarm(self.is_armed)

        if self.is_armed:
            self.btn_arm.setText("DISARM (Motorlari Kilitle)")
            self.btn_arm.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px;")
        else:
            self.btn_arm.setText("ARM (Motorlari Kilitle Ac)")
            self.btn_arm.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 8px;")

    def on_set_mode_clicked(self):
        selected_mode = self.mode_combo.currentText()
        self.worker.change_mode(selected_mode)

    def closeEvent(self, event):
        print("Pencere kapatılıyor...")
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.stop()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
