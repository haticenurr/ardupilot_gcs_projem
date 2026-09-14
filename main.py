import sys
import time
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QGroupBox
from PyQt5.QtCore import QThread, pyqtSignal


class TelemetryWorker(QThread):
    telemetry_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.drone = None

    def run(self):
        try:
            from drone_telemetry import DroneTelemetry
            self.drone = DroneTelemetry()
        except Exception as e:
            print(f"Bağlantı başlatılamadı: {e}")
            return

        while self.is_running:
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GCS Ana Ekran - Drone Telemetri")
        self.resize(400, 300)

        self.setup_ui()

        print("Ağ dinleme işlemi arka planda başlatılıyor...")
        self.worker = TelemetryWorker()
        self.worker.telemetry_signal.connect(self.update_telemetry_ui)
        self.worker.start()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        attitude_group = QGroupBox("Yönelim (Attitude)")
        attitude_layout = QVBoxLayout()
        self.lbl_pitch = QLabel("Pitch: Bekleniyor...")
        self.lbl_roll = QLabel("Roll: Bekleniyor...")
        self.lbl_yaw = QLabel("Yaw: Bekleniyor...")

        font = self.lbl_pitch.font()
        font.setPointSize(12)
        for lbl in [self.lbl_pitch, self.lbl_roll, self.lbl_yaw]:
            lbl.setFont(font)
            attitude_layout.addWidget(lbl)

        attitude_group.setLayout(attitude_layout)
        main_layout.addWidget(attitude_group)

        position_group = QGroupBox("Küresel Konum (Global Position)")
        position_layout = QVBoxLayout()
        self.lbl_lat = QLabel("Enlem (Lat): Bekleniyor...")
        self.lbl_lon = QLabel("Boylam (Lon): Bekleniyor...")
        self.lbl_alt = QLabel("İrtifa (Alt): Bekleniyor...")

        for lbl in [self.lbl_lat, self.lbl_lon, self.lbl_alt]:
            lbl.setFont(font)
            position_layout.addWidget(lbl)

        position_group.setLayout(position_layout)
        main_layout.addWidget(position_group)

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
