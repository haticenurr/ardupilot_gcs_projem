"""
main_v7.py
----------
Modern, koyu temali otonom ucus Yer Istasyonu (GCS).
PyQt5 arayuzu + QThread uzerinden PyMAVLink telemetri.

MAVLink kurali: self.master'a yalnizca TelemetryWorker.run() dokunur.
GUI komutlari command_queue uzerinden iletilir.
"""

import math
import os
import queue
import sys
import time
from datetime import datetime

from PyQt5.QtCore import QThread, Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.map_widget_v3 import DroneMapWidget
from ui.mission_panel import MissionPanel
from ui.stat_card import StatCard, make_badge
from ui.safety_panel import PrearmPanel
from ui.event_log_panel import EventLogPanel
from ui.connection_dialog import ConnectionDialog
from core.flight_logger import FlightLogger
from core.app_paths import logs_dir
from core.voice_alerts import VoiceAlerts
from ui.artificial_horizon import ArtificialHorizon
from ui.replay_panel import ReplayPanel
from ui.mission_mode_selector import MissionModeSelector
from ui.preflight_checklist_dialog import PreflightChecklistDialog
from ui.flight_summary_dialog import FlightSummaryDialog
from ui.parameter_editor_dialog import ParameterEditorDialog
from ui.calibration_dialog import CalibrationDialog

if getattr(sys, "frozen", False):
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    # Tek dosya paketinde matplotlib'in yapilandirma dizini her calistirmada
    # silinen gecici klasore dusuyor; bu yuzden font onbellegi HER ACILISTA
    # yeniden kuruluyor (macOS'ta system_profiler cagrildigi icin onlarca
    # saniye). Onbellegi calistirilabilir dosyanin yanina sabitliyoruz:
    # ilk acilis bir kez yavas, sonrakiler hizli olur.
    _mpl_cache = os.path.join(
        os.path.dirname(os.path.abspath(sys.executable)), ".mpl-cache"
    )
    os.makedirs(_mpl_cache, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", _mpl_cache)
UDP_ENDPOINT = "udp:127.0.0.1:14550"
UDP_BADGE_TEXT = "UDP 14550"
DEFAULT_TAKEOFF_ALT = 20
HEARTBEAT_TIMEOUT_S = 8.0
TAKEOFF_ALT_TOLERANCE_M = 1.5
TAKEOFF_TIMEOUT_S = 45.0

DARK_STYLESHEET = """
    QMainWindow, QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
        font-size: 13px;
    }
    QTabWidget::pane {
        border: 1px solid #313244;
        border-radius: 10px;
        background: #181825;
        top: -1px;
    }
    QTabBar::tab {
    background: #181825;
    color: #a6adc8;
    padding: 8px 16px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    } 
    QTabBar::tab:first {
    min-width: 180px;
    padding-right: 22px;
    }
    QTabBar::tab:selected {
        background: #313244;
        color: #89dceb;
    }
    QGroupBox {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 12px;
        margin-top: 14px;
        padding: 12px 10px 10px 10px;
        font-weight: 700;
        color: #89b4fa;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }
    QLabel {
        background: transparent;
        color: #cdd6f4;
    }
    QPushButton {
        background-color: #313244;
        color: #cdd6f4;
        border: none;
        border-radius: 8px;
        padding: 8px 12px;
        font-weight: 700;
    }
    QPushButton:hover {
        background-color: #45475a;
    }
    QPushButton:pressed {
        background-color: #585b70;
    }
    QPushButton:disabled {
        background-color: #313244;
        color: #6c7086;
    }
    QComboBox, QSpinBox {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 6px 10px;
        min-height: 22px;
    }
    QComboBox QAbstractItemView {
        background-color: #1e1e2e;
        color: #cdd6f4;
        selection-background-color: #45475a;
    }
    QSplitter::handle {
        background: #313244;
        width: 4px;
    }
    QMessageBox {
        background-color: #1e1e2e;
    }
    QScrollArea {
        background-color: transparent;
        border: none;
    }
    QScrollBar:vertical {
        background: #181825;
        width: 10px;
        margin: 0;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #45475a;
        min-height: 24px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background: #89b4fa;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QStatusBar {
        background-color: #181825;
        color: #cdd6f4;
        border-top: 1px solid #313244;
        font-weight: 600;
        padding: 4px 10px;
    }
    QStatusBar::item {
        border: none;
    }
"""


def haversine_m(lat1, lon1, lat2, lon2):
    """Iki WGS84 noktasi arasindaki buyuk daire mesafesi (metre)."""
    r_earth = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    # ONEMLI DUZELTME: iki nokta birbirine COK yaklastiginda (hedefe/eve
    # neredeyse ulasildiginda), ondalik yuvarlama hatasi yuzunden 'a' ufak
    # NEGATIF bir sayi olabiliyor (orn. -1e-16). math.sqrt(negatif) Python'da
    # "math domain error" ile COKUYOR. Eski kod sadece ust siniri (1.0)
    # kirpiyordu, alt siniri (0.0) kirpmiyordu. max(0.0, ...) ekleyerek bu
    # cokmeyi tamamen onluyoruz - bu cokme, mesafe kartlarinin hedefe/eve
    # yaklasildiginda guncellenmeyi durdurmasina (donuk kalmasina) sebep
    # oluyordu.
    a = max(0.0, min(1.0, a))
    return 2 * r_earth * math.asin(math.sqrt(a))


class TelemetryWorker(QThread):
    telemetry_signal = pyqtSignal(dict)
    connection_status_signal = pyqtSignal(bool, str)
    mission_upload_result = pyqtSignal(bool, str)
    mission_download_result = pyqtSignal(bool, str, list)
    mission_clear_result = pyqtSignal(bool, str)
    wizard_status = pyqtSignal(str, bool)  # mesaj, devam_ediyor_mu
    arm_result = pyqtSignal(bool, str)   
    goto_result = pyqtSignal(bool, str)
    param_value_received = pyqtSignal(dict)
    fence_polygon_upload_result = pyqtSignal(bool, str)
    fence_polygon_download_result = pyqtSignal(bool, str, list)
    fence_polygon_clear_result = pyqtSignal(bool, str)
    

    def __init__(self, connection_string=UDP_ENDPOINT):
        super().__init__()
        self.connection_string = connection_string
        self.is_running = True
        self.drone = None
        # GUI thread yalnizca buraya yazar; MAVLink I/O run() icinde yapilir
        self.command_queue = queue.Queue()
        self._last_traffic = time.time()
        self._lost_emitted = False
        self._was_armed= False
        self._last_prearm_poll = 0.0
        # Telemetri hatalarini sessizce yutmak yerine kisik sesle raporlamak
        # icin (bkz. _log_telemetry_error).
        # ARM reddedildiginde sebebi kullaniciya gosterebilmek icin son
        # PreArm/Arm uyarisi burada tutulur.
        self._last_prearm_text = ""
        self._last_prearm_ts = 0.0
        self._last_error_sig = None
        self._last_error_ts = 0.0
        self._suppressed_errors = 0

    def run(self):
        try:
            from core.drone_telemetry import DroneTelemetry
            self.drone = DroneTelemetry(self.connection_string)
            # Uzun mission/fence islemleri sirasinda yakalanan telemetri de
            # ayni yoldan yayinlansin; aksi halde o saniyelerde arayuz donuk
            # kaliyor ve heartbeat zaman asimi sahte alarm uretiyordu.
            self.drone.telemetry_sink = self._publish
            self._last_traffic = time.time()
            self.connection_status_signal.emit(True, "Baglanti basarili")
        except Exception as e:
            print(f"Baglanti baslatilamadi: {e}")
            self.connection_status_signal.emit(False, str(e))
            return

        try:
            while self.is_running:
                try:
                    cmd = self.command_queue.get_nowait()
                except queue.Empty:
                    cmd = None

                if cmd:
                    self._handle_command(cmd)
                    continue

                try:
                    if self.drone:
                        data = self.drone.get_telemetry_data()
                        if data:
                            self._publish(data)
                except Exception as e:
                    self._log_telemetry_error(e)

                if (
                    not self._lost_emitted
                    and (time.time() - self._last_traffic) > HEARTBEAT_TIMEOUT_S
                ):
                    self._lost_emitted = True
                    self.connection_status_signal.emit(False, "Zaman asimi: telemetri kesildi")

                # DISARM durumdayken, PreArm mesajlarinin listede "canli"
                # kalmasi icin 4 saniyede bir otopilottan kontrolleri
                # yeniden calistirmasini istiyoruz (gercek ARM denemesi
                # DEGIL, sadece kontrol sonucu STATUSTEXT'i tazeler).
                now = time.time()
                if (
                    self.drone
                    and not self._was_armed
                    and (now - self._last_prearm_poll) > 4.0
                ):
                    self._last_prearm_poll = now
                    try:
                        self.drone.request_prearm_check()
                    except Exception as e:
                        self._log_telemetry_error(e)

                time.sleep(0.05)
        finally:
            if self.drone:
                self.drone.close()
                self.drone = None

    def _publish(self, data):
        """Telemetriyi GUI'ye ileten TEK nokta. Hem ana dongu hem de
        DroneTelemetry'nin uzun protokol beklemeleri sirasinda yakaladigi
        mesajlar buradan gecer; boylece 'son trafik' zamani ve toparlanma
        bildirimi her iki yolda da ayni sekilde isler."""
        self._last_traffic = time.time()
        if self._lost_emitted:
            self._lost_emitted = False
            self.connection_status_signal.emit(True, "Baglanti toparlandi")
        self._process_telemetry_data(data)
        self.telemetry_signal.emit(data)

    def _arm_hata_sebebi(self, taban_mesaj: str) -> str:
        """ARM basarisizligina, varsa otopilotun bildirdigi sebebi ekler.
        Tek basina "ARM gerceklesmedi" kullaniciya ne yapacagini
        soylemiyordu; asil bilgi PreArm STATUSTEXT'inde."""
        if self._last_prearm_text and (time.time() - self._last_prearm_ts) < 15.0:
            return f"{taban_mesaj} — {self._last_prearm_text}"
        return taban_mesaj

    def _log_telemetry_error(self, exc):
        """Telemetri hatalarini yutmak yerine raporlar. Dongu saniyede ~20
        kez dondugu icin ayni hata en fazla 5 saniyede bir yazdirilir;
        bastirilan tekrar sayisi bir sonraki satirda belirtilir."""
        now = time.time()
        signature = f"{type(exc).__name__}: {exc}"
        if signature == self._last_error_sig and (now - self._last_error_ts) < 5.0:
            self._suppressed_errors += 1
            return
        suffix = ""
        if self._suppressed_errors:
            suffix = f" (onceki {self._suppressed_errors} tekrar bastirildi)"
        self._last_error_sig = signature
        self._last_error_ts = now
        self._suppressed_errors = 0
        print(f"[TelemetryWorker] Telemetri hatasi: {signature}{suffix}")

    def _handle_command(self, cmd):
        name = cmd.get("cmd")
        if not self.drone:
            return
        try:
            if name == "arm":
                success, message = self.drone.send_arm_disarm(bool(cmd.get("arm")))
                if not success:
                    message = self._arm_hata_sebebi(message)
                self.arm_result.emit(success, message)
            elif name == "set_mode":
                self.drone.set_mode(cmd.get("mode", ""))
            elif name == "takeoff":
                self.drone.takeoff(float(cmd.get("altitude", DEFAULT_TAKEOFF_ALT)))
            elif name == "upload_mission":
                success, message = self.drone.upload_mission(cmd.get("waypoints") or [])
                self.mission_upload_result.emit(success, message)
            elif name == "download_mission":
                success, message, waypoints = self.drone.download_mission()
                self.mission_download_result.emit(success, message, waypoints)
            elif name == "clear_mission":
                success, message = self.drone.clear_mission()
                self.mission_clear_result.emit(success, message)
            elif name == "fly_mission":
                self._run_fly_mission(float(cmd.get("altitude", DEFAULT_TAKEOFF_ALT)))
            elif name == "request_fence":
                self.drone.request_fence_params()
            elif name == "request_failsafe_params":
                self.drone.request_failsafe_params()
            elif name == "set_rtl_alt":
                self.drone.set_rtl_altitude(float(cmd.get("altitude")))
            elif name == "start_mag_cal":
                self.drone.start_mag_cal()
            elif name == "accept_mag_cal":
                self.drone.accept_mag_cal()
            elif name == "cancel_mag_cal":
                self.drone.cancel_mag_cal()
            elif name == "start_accel_cal":
                self.drone.start_accel_cal()
            elif name == "accel_cal_position":
                self.drone.send_accel_cal_position(int(cmd.get("position")))
            elif name == "start_level_cal":
                self.drone.start_level_cal()
            elif name == "start_gyro_cal":
                self.drone.start_gyro_cal()
            elif name == "start_baro_cal":
                self.drone.start_baro_cal()
            elif name == "request_single_param":
                self.drone.request_single_param(cmd.get("name"))                
            elif name == "set_fence":
                self.drone.set_fence_params(bool(cmd.get("enabled")), float(cmd.get("radius", 100)))
                self.drone.request_fence_params()
            elif name == "request_all_params":
                self.drone.request_all_params()
            elif name == "set_param":
                self.drone.set_param(
                    cmd.get("name"), float(cmd.get("value")), int(cmd.get("param_type", 9))
                )
            elif name == "goto_position":
                success, message = self.drone.goto_position(
                    float(cmd.get("lat")), float(cmd.get("lon")), float(cmd.get("altitude", 20))
                )
                self.goto_result.emit(success, message)
            elif name == "upload_fence_polygon":
                success, message = self.drone.upload_fence_polygon(cmd.get("points") or [])
                self.fence_polygon_upload_result.emit(success, message)
            elif name == "download_fence_polygon":
                success, message, points = self.drone.download_fence_polygon()
                self.fence_polygon_download_result.emit(success, message, points)
            elif name == "clear_fence_polygon":
                success, message = self.drone.clear_fence_polygon()
                self.fence_polygon_clear_result.emit(success, message)                
        except Exception as e:
            print(f"[TelemetryWorker] Komut hatasi ({name}): {e}")
            if name == "upload_mission":
                self.mission_upload_result.emit(False, str(e))
            elif name == "download_mission":
                self.mission_download_result.emit(False, str(e), [])
            elif name == "clear_mission":
                self.mission_clear_result.emit(False, str(e))
            elif name == "fly_mission":
                self.wizard_status.emit(f"Gorev sihirbazi hata: {e}", False)

    def _pump_telemetry(self):
        """Uzun beklemelerde GUI'nin donmamasi icin mesajlari iletmeye devam et."""
        if not self.drone:
            return None
        data = self.drone.get_telemetry_data()
        if data:
            self._publish(data)
        return data
        
    def _process_telemetry_data(self, data):
        """
        HEARTBEAT'teki DISARMED->ARMED gecisini izler. ArduCopter her ARM
        ediliginde 'home' konumunu o anki pozisyona sifirlar/gunceller.
        Baglanti kurulur kurulmaz aldigimiz eski home degeri bu yuzden
        her yeni ARM sonrasi gecersiz kalabilir ("Eve Mesafe" hicbir
        zaman 0'a inmez). Yeni bir ARM tespit edildiginde home konumunu
        FC'den tekrar istiyoruz.
        """
        if data.get("type") == "STATUSTEXT":
            metin = (data.get("text") or "").strip()
            dusuk = metin.lower()
            if dusuk.startswith("prearm:") or dusuk.startswith("arm:"):
                self._last_prearm_text = metin
                self._last_prearm_ts = time.time()
            return

        if data.get("type") == "HEARTBEAT":
            armed_now = bool(data.get("armed"))
            if armed_now and not self._was_armed:
                try:
                    self.drone.request_home_position()
                except Exception as e:
                    self._log_telemetry_error(e)
            self._was_armed = armed_now

    def _wait_heartbeat(self, predicate, timeout_s, status_text):
        self.wizard_status.emit(status_text, True)
        deadline = time.time() + timeout_s
        while self.is_running and time.time() < deadline:
            data = self._pump_telemetry()
            if data and data.get("type") == "HEARTBEAT" and predicate(data):
                return True
            time.sleep(0.05)
        return False

    def _wait_altitude(self, target_m, timeout_s):
        deadline = time.time() + timeout_s
        while self.is_running and time.time() < deadline:
            data = self._pump_telemetry()
            if data and data.get("type") == "GLOBAL_POSITION_INT":
                alt = float(data.get("alt") or 0.0)
                if alt >= target_m - TAKEOFF_ALT_TOLERANCE_M:
                    return True, alt
            time.sleep(0.05)
        return False, None

    def _wait_mission_current(self, target_seq, timeout_s):
        """FC'nin MISSION_SET_CURRENT istegini isledigini MISSION_CURRENT
        mesajiyla dogrular. Bu olmadan AUTO'ya gecilirse eski index'ten
        devam etme riski surer."""
        deadline = time.time() + timeout_s
        while self.is_running and time.time() < deadline:
            data = self._pump_telemetry()
            if data and data.get("type") == "MISSION_CURRENT" and data.get("seq") == target_seq:
                return True
            time.sleep(0.05)
        return False

    def _run_fly_mission(self, altitude_m):
        """
        ARM -> GUIDED -> TAKEOFF -> irtifa dogrula -> AUTO + MISSION_START
        Tum MAVLink I/O bu thread icinde kalir.
        """
        try:
            self.wizard_status.emit("Arm ediliyor...", True)
            # Eski kod bu donusu YOK SAYIYORDU; FC komutu aciktan
            # reddettiginde bile 12 saniye bekleyip "ARM gerceklesmedi"
            # diyordu ve sebebi hic gostermiyordu.
            arm_ok, arm_mesaj = self.drone.send_arm_disarm(True)
            if not arm_ok:
                self.wizard_status.emit(
                    f"Hata: {self._arm_hata_sebebi(arm_mesaj)}", False
                )
                return
            armed = self._wait_heartbeat(
                lambda d: bool(d.get("armed")),
                12.0,
                "Arm bekleniyor...",
            )
            if not armed:
                self.wizard_status.emit(
                    f"Hata: {self._arm_hata_sebebi('ARM gerceklesmedi')}", False
                )
                return

            self.wizard_status.emit("GUIDED moda geciliyor...", True)
            self.drone.set_mode("GUIDED")
            guided = self._wait_heartbeat(
                lambda d: (d.get("mode") or "").upper() == "GUIDED",
                8.0,
                "GUIDED bekleniyor...",
            )
            if not guided:
                self.wizard_status.emit("Hata: GUIDED moda gecilemedi", False)
                return

            self.wizard_status.emit("Kalkis yapiliyor...", True)
            self.drone.takeoff(altitude_m)
            reached, alt = self._wait_altitude(altitude_m, TAKEOFF_TIMEOUT_S)
            if not reached:
                self.wizard_status.emit(
                    f"Hata: {altitude_m:.0f} m irtifaya ulasilamadi (zaman asimi)",
                    False,
                )
                return

            self.wizard_status.emit(
                f"Irtifaya ulasildi ({alt:.1f} m), waypoint 1'e sifirlaniyor...",
                True,
            )
            # KRITIK: AUTO moduna gecmeden once FC'deki "su anki waypoint"
            # index'ini acikca 1'e cekiyoruz (seq=0 ArduPilot'ta home icin
            # rezerve; gercek 1. waypoint upload_mission() tarafindan seq=1'e
            # yazildi). Aksi halde ArduCopter onceki bir gorev denemesinden
            # kalan index'ten devam edebilir.
            self.drone.set_current_waypoint(1)
            current_reset = self._wait_mission_current(1, 5.0)
            if not current_reset:
                self.wizard_status.emit(
                    "Uyari: waypoint 1 onayi alinamadi, yine de devam ediliyor...",
                    True,
                )

            self.wizard_status.emit("Gorev baslatiliyor...", True)
            self.drone.set_mode("AUTO")
            time.sleep(0.4)
            self.drone.start_mission()
            auto_ok = self._wait_heartbeat(
                lambda d: (d.get("mode") or "").upper() == "AUTO",
                8.0,
                "AUTO moda geciliyor...",
            )
            if auto_ok:
                self.wizard_status.emit("Gorev AUTO modda baslatildi", False)
            else:
                self.wizard_status.emit(
                    "Irtifa OK; AUTO teyit edilemedi, MISSION_START gonderildi",
                    False,
                )
        except Exception as e:
            self.wizard_status.emit(f"Gorev sihirbazi hata: {e}", False)

    def stop(self):
        self.is_running = False
        if not self.wait(8000):
            print("[TelemetryWorker] Thread zamaninda durmadi, terminate")
            self.terminate()
            self.wait(1500)

    def enqueue(self, **kwargs):
        self.command_queue.put(kwargs)

    def arm_disarm(self, arm: bool):
        self.enqueue(cmd="arm", arm=arm)

    def change_mode(self, mode_name: str):
        self.enqueue(cmd="set_mode", mode=mode_name)

    def takeoff(self, altitude_m: float):
        self.enqueue(cmd="takeoff", altitude=altitude_m)

    def upload_mission(self, waypoints):
        self.enqueue(cmd="upload_mission", waypoints=waypoints)

    def download_mission(self):
        self.enqueue(cmd="download_mission")

    def clear_mission(self):
        self.enqueue(cmd="clear_mission")

    def fly_mission(self, altitude_m: float):
        self.enqueue(cmd="fly_mission", altitude=altitude_m)

    def request_fence(self):
        self.enqueue(cmd="request_fence")

    def set_fence(self, enabled: bool, radius_m: float):
        self.enqueue(cmd="set_fence", enabled=enabled, radius=radius_m)

    def goto_position(self, lat: float, lon: float, altitude_m: float):
        self.enqueue(cmd="goto_position", lat=lat, lon=lon, altitude=altitude_m)

    def request_all_params(self):
        self.enqueue(cmd="request_all_params")

    def set_param(self, name: str, value: float, param_type: int):
        self.enqueue(cmd="set_param", name=name, value=value, param_type=param_type)

    def set_rtl_altitude(self, alt_m: float):
        self.enqueue(cmd="set_rtl_alt", altitude=alt_m)

    def start_mag_cal(self):
        self.enqueue(cmd="start_mag_cal")

    def accept_mag_cal(self):
        self.enqueue(cmd="accept_mag_cal")

    def cancel_mag_cal(self):
        self.enqueue(cmd="cancel_mag_cal")

    def start_accel_cal(self):
        self.enqueue(cmd="start_accel_cal")

    def send_accel_cal_position(self, position: int):
        self.enqueue(cmd="accel_cal_position", position=position)

    def start_level_cal(self):
        self.enqueue(cmd="start_level_cal")

    def start_gyro_cal(self):
        self.enqueue(cmd="start_gyro_cal")

    def start_baro_cal(self):
        self.enqueue(cmd="start_baro_cal")

    def request_single_param(self, name: str):
        self.enqueue(cmd="request_single_param", name=name)
    def upload_fence_polygon(self, points):
        self.enqueue(cmd="upload_fence_polygon", points=points)

    def download_fence_polygon(self):
        self.enqueue(cmd="download_fence_polygon")

    def clear_fence_polygon(self):
        self.enqueue(cmd="clear_fence_polygon")        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GCS v7 — Otonom Ucus Yer Istasyonu")
        self.setMinimumSize(900, 560)
        self.resize(1280, 760)

        self.is_armed = False
        self.connected = False
        self.current_mode = "--"
        self.current_lat = None
        self.current_lon = None
        self.current_alt = None
        self.current_groundspeed = None
        self.current_heading = None
        self.current_battery = None
        self.flight_logger = FlightLogger(log_dir=logs_dir())
        # Kritik uyarilarin sesli anonsu. Sistemde TTS yoksa available
        # False olur ve ozellik sessizce devre disi kalir.
        self.voice = VoiceAlerts(enabled=True)
        self._was_armed = False
        self._summary_dialog_open = False
        # Biten ucusun ozeti burada saklanir; pencere DISARM aninda
        # kendiliginden acilmaz, pilot "SON UCUS OZETI" butonuyla acar.
        self._last_flight_summary = None
        self.home_lat = None
        self.home_lon = None
        self.mission_current_seq = None
        self.mission_on_vehicle = False
        self.wizard_running = False
        self._ignore_wp_dirty = False
        self._pending_mission_clear_on_connect = False
        self.worker = None
        self.connection_string = UDP_ENDPOINT
        self.mission_mode = "Standart"   
        self.fence_enabled = None
        self.fence_radius = None 
        self.batt_fs_enabled = None
        self.batt_fs_volt = None 
        self._low_battery_warned = False  
        self._was_ever_connected = False
        self._alarm_flash_on = False
        self._conn_alarm_timer = QTimer(self)
        self._conn_alarm_timer.setInterval(500)
        self._conn_alarm_timer.timeout.connect(self._toggle_connection_alarm) 
        self.current_satellites = None
        self.current_rssi = None
        self._flight_max_alt = None
        self._flight_max_speed = None
        self._flight_min_battery = None
        self._flight_distance_m = 0.0
        self._flight_last_pos = None
        self._flight_mode_changes = 0
        self._flight_last_mode = None
        self._flight_min_satellites = None
        self._flight_fence_breach = False
        self._flight_start_iso = None
        self._flight_start_ts = None
        self._flight_timer = QTimer(self)
        self._flight_timer.setInterval(1000)
        self._flight_timer.timeout.connect(self._update_flight_timer_label)
        self.guided_click_active = False
        self.param_editor_dialog = None
        self.calibration_dialog = None
        self.fence_polygon_points = []
        self.polygon_edit_active = False        
        self._fence_type_pending_polygon_fix = False
        self.setup_ui()
        self._start_worker()

    def _start_worker(self):
        print("MAVLink okuma dongusu arka planda baslatiliyor...")
        self.worker = TelemetryWorker(self.connection_string)
        self.worker.telemetry_signal.connect(self.update_telemetry_ui)
        self.worker.connection_status_signal.connect(self.update_connection_status)
        self.worker.mission_upload_result.connect(self.on_mission_upload_result)
        self.worker.mission_download_result.connect(self.on_mission_download_result)
        self.worker.mission_clear_result.connect(self.on_mission_clear_result)
        self.worker.wizard_status.connect(self.on_wizard_status)
        self.worker.arm_result.connect(self.on_arm_result)
        self.worker.goto_result.connect(self.on_goto_result)
        self.worker.fence_polygon_upload_result.connect(self.on_fence_polygon_upload_result)
        self.worker.fence_polygon_download_result.connect(self.on_fence_polygon_download_result)   
        self.worker.fence_polygon_clear_result.connect(self.on_fence_polygon_clear_result)     
        self.worker.start()

    def _disconnect_worker(self, worker):
        if worker is None:
            return
        for signal in (
            worker.telemetry_signal,
            worker.connection_status_signal,
            worker.mission_upload_result,
            worker.mission_download_result,
            worker.mission_clear_result,
            worker.wizard_status,
            worker.arm_result,
            worker.goto_result,
            worker.fence_polygon_upload_result,
            worker.fence_polygon_download_result,
            worker.fence_polygon_clear_result,
        ):
            try:
                signal.disconnect()
            except TypeError:
                pass

    def setup_ui(self):
        central = QWidget()
        central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCentralWidget(central)
        self.central_widget = central
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 4)
        root.setSpacing(8)

        header = self._build_status_bar()
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(header, 0)
        mode_row = QFrame()
        mode_row.setObjectName("modeRow")
        mode_row.setStyleSheet("""
            QFrame#modeRow {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 12px;
            }
        """)
        mode_row_layout = QHBoxLayout(mode_row)
        mode_row_layout.setContentsMargins(10, 6, 10, 6)
        mode_row_layout.addStretch(1)
        self.mission_mode_selector = MissionModeSelector()
        self.mission_mode_selector.setFixedWidth(480)
        self.mission_mode_selector.mode_changed.connect(self.on_mission_mode_changed)
        mode_row_layout.addWidget(self.mission_mode_selector)
        mode_row_layout.addStretch(1)
        mode_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(mode_row, 0)

        tabs = QTabWidget()
        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tabs.setElideMode(Qt.ElideNone)
        tabs.tabBar().setUsesScrollButtons(True)

        telemetry_page = self._wrap_scroll(self._build_telemetry_tab())

        self.map_widget = DroneMapWidget()
        self.map_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.map_widget.setMinimumSize(280, 200)

        self.mission_panel = MissionPanel()
        self.mission_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.mission_panel.waypoints_changed.connect(self.on_waypoints_changed)
        self.mission_panel.upload_requested.connect(self.on_mission_upload_requested)
        self.mission_panel.download_requested.connect(self.on_mission_download_requested)
        self.mission_panel.clear_mission_requested.connect(self.on_mission_clear_requested)
        self.mission_panel.status_message.connect(self.show_transient_status)
        self.map_widget.waypoint_added.connect(self.mission_panel.add_waypoint)
        self.map_widget.set_mission_editing(False)
        self.map_widget.guided_goto_requested.connect(self.on_guided_goto_requested)
        self.map_widget.fence_point_added.connect(self.on_fence_point_added)        
        mission_page = self._wrap_scroll(self.mission_panel)

        self.safety_panel = PrearmPanel()
        self.safety_panel.fence_settings_changed.connect(self.on_fence_settings_changed)
        self.safety_panel.rtl_alt_changed.connect(self.on_rtl_alt_changed)
        self.safety_panel.battery_fs_changed.connect(self.on_battery_fs_changed)
        self.safety_panel.polygon_draw_toggled.connect(self.on_polygon_draw_toggled)
        self.safety_panel.polygon_undo_requested.connect(self.on_polygon_undo_requested)
        self.safety_panel.polygon_clear_requested.connect(self.on_polygon_clear_requested)
        self.safety_panel.polygon_upload_requested.connect(self.on_polygon_upload_requested)
        self.safety_panel.polygon_download_requested.connect(self.on_polygon_download_requested)        
        safety_page = self._wrap_scroll(self.safety_panel)

        self.event_log_panel = EventLogPanel()

        self.replay_panel = ReplayPanel(log_dir=logs_dir())
        self.replay_panel.sample_ready.connect(self.on_replay_sample)
        self.replay_panel.state_changed.connect(self.on_replay_state_changed)
        self.replay_panel.clear_requested.connect(self.map_widget.clear_flight_path)

        self._tab_pages = {
            "Telemetri ve Kontrol": telemetry_page,
            "Ucus Plani": mission_page,
            "Guvenlik": safety_page,
            "Olay Gunlugu": self.event_log_panel,
            "Ucus Tekrari": self.replay_panel,
        }
        self.tabs = tabs
        self._apply_tab_order(self.MISSION_MODE_TAB_ORDER["Standart"], animate=False)
        tabs.currentChanged.connect(self.on_tab_changed)

        # PreArm uyarilarinin "cozulmus" sayilip listeden dusurulmesi icin
        # periyodik kontrol (safety_panel.py'nin kendi PREARM_STALE_S suresine
        # gore calisir, burada sadece duzenli olarak tetikliyoruz).
        self._safety_timer = QTimer(self)
        self._safety_timer.setInterval(2000)
        self._safety_timer.timeout.connect(self.safety_panel.tick)
        self._safety_timer.start()



        left_panel = QWidget()
        left_panel.setMinimumWidth(400)
        left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(tabs)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.map_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 860])
        root.addWidget(splitter, 1)

        status = QStatusBar()
        status.setSizeGripEnabled(True)
        status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStatusBar(status)
        self.show_transient_status("Hazir")
        self._update_action_buttons()

    def _build_status_bar(self):
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setStyleSheet("""
            QFrame#statusBar {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 12px;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        title = QLabel("YER ISTASYONU")
        title.setStyleSheet(
            "color: #89dceb; font-size: 14px; font-weight: 800; letter-spacing: 1.5px;"
        )
        layout.addWidget(title)

        subtitle = QLabel("MAVLink · Canli Telemetri")
        subtitle.setStyleSheet("color: #6c7086; font-size: 12px; font-weight: 600;")
        layout.addWidget(subtitle)
        layout.addStretch()

        self.badge_connection = make_badge(f"{UDP_BADGE_TEXT} · BEKLENIYOR", "#45475a", "#cdd6f4")
        self.badge_arm = make_badge("DISARMED", "#f38ba8", "#1e1e2e")
        self.badge_mode = make_badge("MOD: --", "#89b4fa", "#1e1e2e")
        self.badge_flight_timer = make_badge("SURE: --:--", "#a6e3a1", "#1e1e2e")


        self.btn_reconnect = QPushButton("Yeniden Baglan")
        self.btn_reconnect.setCursor(Qt.PointingHandCursor)
        self.btn_reconnect.clicked.connect(self.on_reconnect_clicked)
        
        self.btn_connection_settings = QPushButton("Baglanti Ayarlari")
        self.btn_connection_settings.setCursor(Qt.PointingHandCursor)
        self.btn_connection_settings.clicked.connect(self.on_connection_settings_clicked)
        self.btn_param_editor = QPushButton("Parametreler")
        self.btn_param_editor.setCursor(Qt.PointingHandCursor)
        self.btn_param_editor.clicked.connect(self.on_param_editor_clicked)
        self.btn_calibration = QPushButton("Kalibrasyon")
        self.btn_calibration.setCursor(Qt.PointingHandCursor)
        self.btn_calibration.clicked.connect(self.on_calibration_clicked)

        self.btn_voice = QPushButton()
        self.btn_voice.setCursor(Qt.PointingHandCursor)
        self.btn_voice.clicked.connect(self.on_voice_toggle_clicked)
        self._refresh_voice_button()
        layout.addWidget(self.badge_connection)
        layout.addWidget(self.badge_arm)
        layout.addWidget(self.badge_mode)
        layout.addWidget(self.badge_flight_timer)

        layout.addWidget(self.btn_reconnect)
        layout.addWidget(self.btn_connection_settings)
        layout.addWidget(self.btn_param_editor)
        layout.addWidget(self.btn_calibration)
        layout.addWidget(self.btn_voice)
        self._style_reconnect_button(attention=False)
        return bar

    def _wrap_scroll(self, inner: QWidget) -> QScrollArea:
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setWidget(inner)
        return scroll

    def _build_telemetry_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(10)
        layout.setSizeConstraint(QVBoxLayout.SetMinimumSize)

        self.artificial_horizon = ArtificialHorizon()
        layout.addWidget(self.artificial_horizon, alignment=Qt.AlignHCenter)

        cards = QGridLayout()
        cards.setSpacing(10)

        self.card_alt = StatCard("Irtifa", "m", "#89dceb")
        self.card_gs = StatCard("Yer Hizi", "m/s", "#89b4fa")
        self.card_hdg = StatCard("Yon", "°", "#94e2d5")
        self.card_bat = StatCard("Pil", "%", "#a6e3a1")
        self.card_gps = StatCard("GPS Uydu", "sat", "#cba6f7")
        self.card_wp = StatCard("Siradaki WP", "#", "#fab387")
        self.card_wp_dist = StatCard("Hedefe Mesafe", "m", "#f9e2af")
        self.card_home_dist = StatCard("Eve Mesafe", "m", "#a6e3a1")
        self.card_rssi = StatCard("Sinyal", "%", "#94e2d5")
        self.card_rssi.setToolTip(
            "Telemetri radyosunun sinyal gucu (RADIO_STATUS). "
            "SITL bu mesaji uretmez, o yuzden simulasyonda '--' kalir."
        )

        for card in (
            self.card_alt, self.card_gs, self.card_hdg, self.card_bat,
            self.card_gps, self.card_wp, self.card_wp_dist, self.card_home_dist,
            self.card_rssi,
        ):
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        cards.addWidget(self.card_alt, 0, 0)
        cards.addWidget(self.card_gs, 0, 1)
        cards.addWidget(self.card_hdg, 1, 0)
        cards.addWidget(self.card_bat, 1, 1)
        cards.addWidget(self.card_gps, 2, 0)
        cards.addWidget(self.card_wp, 2, 1)
        cards.addWidget(self.card_wp_dist, 3, 0)
        cards.addWidget(self.card_home_dist, 3, 1)
        cards.addWidget(self.card_rssi, 4, 0)
        layout.addLayout(cards)

        attitude_group = QGroupBox("Yonelim")
        att_layout = QHBoxLayout()
        self.lbl_pitch = QLabel("Pitch: --")
        self.lbl_roll = QLabel("Roll: --")
        self.lbl_yaw = QLabel("Yaw: --")
        for lbl in (self.lbl_pitch, self.lbl_roll, self.lbl_yaw):
            lbl.setStyleSheet("color: #a6adc8; font-size: 12px; font-weight: 600;")
            att_layout.addWidget(lbl)
        attitude_group.setLayout(att_layout)
        layout.addWidget(attitude_group)

        position_group = QGroupBox("Kuresel Konum")
        pos_layout = QVBoxLayout()
        self.lbl_lat = QLabel("Enlem: --")
        self.lbl_lon = QLabel("Boylam: --")
        for lbl in (self.lbl_lat, self.lbl_lon):
            lbl.setStyleSheet("color: #a6adc8; font-size: 12px; font-weight: 600;")
            pos_layout.addWidget(lbl)
        position_group.setLayout(pos_layout)
        layout.addWidget(position_group)

        control_group = QGroupBox("Komuta ve Kontrol")
        control_layout = QVBoxLayout()

        self.btn_preflight_check = QPushButton("UCUS ONCESI KONTROL LISTESI")
        self.btn_preflight_check.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: 800; padding: 10px; border-radius: 8px;"
        )
        self.btn_preflight_check.clicked.connect(self.on_preflight_check_clicked)
        control_layout.addWidget(self.btn_preflight_check)

        # RTL/LAND sirasinda otopilot kisa sureli, gercek olmayan bir DISARM
        # gorunumu uretebiliyor; ozeti DISARM aninda otomatik acmak bu yuzden
        # pilotun onune beklenmedik anda pencere getiriyordu. Ozet artik
        # saklanir, pilot hazir oldugunda bu butonla acar.
        self.btn_last_summary = QPushButton("SON UCUS OZETI")
        self.btn_last_summary.setCursor(Qt.PointingHandCursor)
        self.btn_last_summary.setEnabled(False)
        self.btn_last_summary.setToolTip(
            "Henuz tamamlanmis bir ucus yok. Ucus DISARM ile bittiginde aktiflesir."
        )
        self.btn_last_summary.clicked.connect(self.on_last_summary_clicked)
        control_layout.addWidget(self.btn_last_summary)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Ucus Adi (opsiyonel)"))
        self.flight_name_input = QLineEdit()
        self.flight_name_input.setPlaceholderText("orn. Test Ucusu 1")
        name_row.addWidget(self.flight_name_input, 1)
        control_layout.addLayout(name_row)

        self.btn_arm = QPushButton("ARM")
        self.btn_arm.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: 800; padding: 10px; border-radius: 8px;"
        )
        self.btn_arm.clicked.connect(self.on_arm_disarm_clicked)
        control_layout.addWidget(self.btn_arm)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Ucus Modu"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["STABILIZE", "GUIDED", "AUTO", "RTL", "LAND", "LOITER"])
        mode_row.addWidget(self.mode_combo, 1)
        self.btn_set_mode = QPushButton("Uygula")
        self.btn_set_mode.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; padding: 8px 14px;"
        )
        self.btn_set_mode.clicked.connect(self.on_set_mode_clicked)
        mode_row.addWidget(self.btn_set_mode)
        control_layout.addLayout(mode_row)

        emergency_row = QHBoxLayout()
        self.btn_rtl = QPushButton("RTL")
        self.btn_rtl.setMinimumHeight(44)
        self.btn_rtl.setStyleSheet(
            "background-color: #fab387; color: #1e1e2e; font-weight: 800; font-size: 15px; border-radius: 10px;"
        )
        self.btn_rtl.setToolTip("Return to Launch — eve don")
        self.btn_rtl.clicked.connect(self.on_rtl_clicked)
        self.btn_land = QPushButton("LAND")
        self.btn_land.setMinimumHeight(44)
        self.btn_land.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: 800; font-size: 15px; border-radius: 10px;"
        )
        self.btn_land.setToolTip("Bulundugu yere inis")
        self.btn_land.clicked.connect(self.on_land_clicked)
        emergency_row.addWidget(self.btn_rtl)
        emergency_row.addWidget(self.btn_land)
        control_layout.addLayout(emergency_row)

        takeoff_row = QHBoxLayout()
        takeoff_row.addWidget(QLabel("Kalkis irtifa (m)"))
        self.spin_takeoff_alt = QSpinBox()
        self.spin_takeoff_alt.setRange(5, 120)
        self.spin_takeoff_alt.setValue(DEFAULT_TAKEOFF_ALT)
        self.spin_takeoff_alt.setSuffix(" m")
        takeoff_row.addWidget(self.spin_takeoff_alt, 1)
        self.btn_takeoff = QPushButton("KALKIS (TAKEOFF)")
        self.btn_takeoff.setStyleSheet(
            "background-color: #89dceb; color: #1e1e2e; font-weight: 800; padding: 10px;"
        )
        self.btn_takeoff.clicked.connect(self.on_takeoff_clicked)
        takeoff_row.addWidget(self.btn_takeoff)
        control_layout.addLayout(takeoff_row)

        self.lbl_takeoff_hint = QLabel("")
        self.lbl_takeoff_hint.setWordWrap(True)
        self.lbl_takeoff_hint.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: 600;")
        control_layout.addWidget(self.lbl_takeoff_hint)

        self.btn_fly_mission = QPushButton("GOREVI UCUR")
        self.btn_fly_mission.setMinimumHeight(48)
        self.btn_fly_mission.setStyleSheet(
            "background-color: #94e2d5; color: #1e1e2e; font-weight: 800; font-size: 15px; border-radius: 10px;"
        )
        self.btn_fly_mission.clicked.connect(self.on_fly_mission_clicked)
        control_layout.addWidget(self.btn_fly_mission)

        self.btn_guided_click = QPushButton("TIKLA VE GIT: KAPALI")
        self.btn_guided_click.setMinimumHeight(40)
        self.btn_guided_click.setCheckable(True)
        self.btn_guided_click.setStyleSheet(
            "background-color: #313244; color: #cdd6f4; font-weight: 800; border-radius: 8px;"
        )
        self.btn_guided_click.setToolTip(
            "Acildiginda haritaya tikladiginiz her nokta, drone'a aninda GUIDED hedefi olarak gonderilir."
        )
        self.btn_guided_click.clicked.connect(self.on_guided_click_toggled)
        control_layout.addWidget(self.btn_guided_click)

        self.lbl_fly_hint = QLabel("")
        self.lbl_fly_hint.setWordWrap(True)
        self.lbl_fly_hint.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: 600;")
        control_layout.addWidget(self.lbl_fly_hint)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        return tab

    def _style_badge(self, badge, text, bg, fg="#1e1e2e"):
        badge.setText(text)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                font-size: 11px;
                font-weight: 700;
                padding: 5px 12px;
                border-radius: 10px;
            }}
        """)

    def _style_reconnect_button(self, attention: bool):
        if attention:
            self.btn_reconnect.setStyleSheet(
                "background-color: #fab387; color: #1e1e2e; font-weight: 800; "
                "padding: 6px 12px; border-radius: 8px;"
            )
        else:
            self.btn_reconnect.setStyleSheet(
                "background-color: #313244; color: #cdd6f4; font-weight: 700; "
                "padding: 6px 12px; border-radius: 8px;"
            )
    def _start_connection_alarm(self):
        if not self._conn_alarm_timer.isActive():
            self._conn_alarm_timer.start()

    def _stop_connection_alarm(self):
        self._conn_alarm_timer.stop()
        self.central_widget.setStyleSheet("")

    def _toggle_connection_alarm(self):
        self._alarm_flash_on = not self._alarm_flash_on
        if self._alarm_flash_on:
            self.central_widget.setStyleSheet(
                "QWidget#centralAlarm { border: 4px solid #f38ba8; }"
            )
            self.central_widget.setObjectName("centralAlarm")
        else:
            self.central_widget.setStyleSheet(
                "QWidget#centralAlarm { border: 4px solid transparent; }"
            )

    def _start_flight_timer(self):
        self._flight_start_ts = time.time()
        self._flight_timer.start()
        self._update_flight_timer_label()

    def _connection_badge_prefix(self):
        cs = self.connection_string or UDP_ENDPOINT
        if cs.startswith(("udp", "tcp")):
            port = cs.rsplit(":", 1)[-1]
            kind = "UDP" if cs.startswith("udp") else "TCP"
            return f"{kind} {port}"
        if "," in cs:
            port, _, baud = cs.partition(",")
            return f"{os.path.basename(port.strip())} {baud.strip()}"
        return cs[:22]

    def _stop_flight_timer(self):
        self._flight_timer.stop()
        elapsed = 0.0
        if self._flight_start_ts is not None:
            elapsed = time.time() - self._flight_start_ts
            minutes, seconds = divmod(int(elapsed), 60)
            self._style_badge(
                self.badge_flight_timer,
                f"SURE: {minutes:02d}:{seconds:02d}",
                "#a6e3a1",
            )
            self._flight_start_ts = None
        return elapsed

    def _update_flight_timer_label(self):
        if self._flight_start_ts is None:
            return
        elapsed = int(time.time() - self._flight_start_ts)
        minutes, seconds = divmod(elapsed, 60)
        self._style_badge(self.badge_flight_timer, f"SURE: {minutes:02d}:{seconds:02d}", "#a6e3a1")

    def _capture_flight_summary(self, duration_s: float):
        """Biten ucusun istatistiklerini saklar ve 'SON UCUS OZETI' butonunu
        aktiflestirir. Pencereyi ACMAZ: RTL/LAND sirasindaki kisa sureli,
        gercek olmayan DISARM gorunumleri pilotun onune beklenmedik anda
        pencere getiriyordu."""
        self._last_flight_summary = {
            "duration_s": duration_s,
            "max_alt": self._flight_max_alt or 0.0,
            "max_speed": self._flight_max_speed or 0.0,
            "distance_m": self._flight_distance_m,
            "min_battery": self._flight_min_battery,
            "min_satellites": self._flight_min_satellites,
            "mode_changes": self._flight_mode_changes,
            "fence_breach": self._flight_fence_breach,
            "start_iso": self._flight_start_iso,
            "flight_name": self.flight_name_input.text().strip(),
            "log_filename": self.flight_logger.get_current_filename(),
        }
        minutes, seconds = divmod(int(duration_s), 60)
        self.btn_last_summary.setEnabled(True)
        self.btn_last_summary.setText(f"SON UCUS OZETI ({minutes:02d}:{seconds:02d})")
        self.btn_last_summary.setToolTip("Biten ucusun ozet raporunu ac")
        self.btn_last_summary.setStyleSheet(
            "background-color: #89dceb; color: #1e1e2e; font-weight: 800; "
            "padding: 10px; border-radius: 8px;"
        )
        self.event_log_panel.add_event(
            "Ucus ozeti hazir — 'SON UCUS OZETI' butonuyla goruntuleyebilirsiniz",
            success=True,
        )
        self.show_transient_status("Ucus ozeti hazir", 4000, success=True)

    def on_last_summary_clicked(self):
        """Saklanan son ucus ozetini gosterir."""
        if not self._last_flight_summary:
            self.show_transient_status(
                "Henuz tamamlanmis bir ucus yok", 3000, success=False
            )
            return
        if self._summary_dialog_open:
            return
        self._summary_dialog_open = True
        try:
            dialog = FlightSummaryDialog(parent=self, **self._last_flight_summary)
            dialog.exec_()
        finally:
            self._summary_dialog_open = False

    def _update_action_buttons(self):
        takeoff_ok = self.connected and self.is_armed and self.current_mode.upper() == "GUIDED"
        self.btn_takeoff.setEnabled(takeoff_ok)
        if takeoff_ok:
            self.lbl_takeoff_hint.setText("ARMED + GUIDED: kalkis gonderilebilir.")
            self.btn_takeoff.setToolTip("MAV_CMD_NAV_TAKEOFF ile belirtilen irtifaya cik")
        else:
            reasons = []
            if not self.connected:
                reasons.append("baglanti yok")
            if not self.is_armed:
                reasons.append("DISARMED")
            if self.current_mode.upper() != "GUIDED":
                reasons.append(f"mod {self.current_mode} (GUIDED gerekli)")
            why = "TAKEOFF kapali: " + ", ".join(reasons)
            self.lbl_takeoff_hint.setText(why)
            self.btn_takeoff.setToolTip(why)

        has_wps = bool(self.mission_panel.waypoints)
        fly_ok = (
            self.connected
            and has_wps
            and self.mission_on_vehicle
            and not self.wizard_running
        )
        self.btn_fly_mission.setEnabled(fly_ok)
        if fly_ok:
            self.lbl_fly_hint.setText("ARM → GUIDED → TAKEOFF → AUTO sirasi otomatik calisir.")
            self.btn_fly_mission.setToolTip("Yuklu gorevi otomatik baslat")
        else:
            fly_reasons = []
            if not self.connected:
                fly_reasons.append("baglanti yok")
            if not has_wps:
                fly_reasons.append("waypoint yok")
            if has_wps and not self.mission_on_vehicle:
                fly_reasons.append("gorev henuz drona yuklenmedi")
            if self.wizard_running:
                fly_reasons.append("sihirbaz calisiyor")
            why = "GOREVI UCUR kapali: " + ", ".join(fly_reasons)
            self.lbl_fly_hint.setText(why)
            self.btn_fly_mission.setToolTip(why)

        rtl_ok = self.connected
        self.btn_rtl.setEnabled(rtl_ok)
        self.btn_land.setEnabled(rtl_ok)
        self.btn_set_mode.setEnabled(self.connected)
        self.btn_arm.setEnabled(self.connected)

    def _refresh_nav_cards(self):
        waypoints = self.mission_panel.waypoints
        seq = self.mission_current_seq
        if seq is None:
            self.card_wp.set_value("--")
            self.card_wp_dist.set_value("--")
        else:
            display_index = seq - 1
            if waypoints and 0 <= display_index < len(waypoints):
                self.card_wp.set_value(str(display_index + 1))
                target = waypoints[display_index]
            else:
                self.card_wp.set_value(str(seq))
                target = None
            if target and self.current_lat is not None:
                dist = haversine_m(
                    self.current_lat, self.current_lon, target[0], target[1]
                )

                self.card_wp_dist.set_value(f"{dist:.0f}")
            else:
                self.card_wp_dist.set_value("--")

        if (
            self.home_lat is not None
            and self.current_lat is not None
        ):
            home_dist = haversine_m(
                self.current_lat, self.current_lon, self.home_lat, self.home_lon
            )

            self.card_home_dist.set_value(f"{home_dist:.0f}")
        else:
            self.card_home_dist.set_value("--")

    def _refresh_geofence(self):
        """Home konumu ve FENCE_ENABLE/FENCE_RADIUS parametreleri elde
        edildiginde haritada dairesel geofence sinirini cizer/gunceller."""
        self.safety_panel.set_fence_display(bool(self.fence_enabled), self.fence_radius)
        if (
            self.fence_enabled
            and self.fence_radius
            and self.home_lat is not None
            and self.home_lon is not None
        ):
            self.map_widget.update_geofence(self.home_lat, self.home_lon, self.fence_radius)
        else:
            self.map_widget.clear_geofence()

    def on_fence_settings_changed(self, enabled: bool, radius_m: float):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: geofence ayari gonderilemedi", 3000, success=False)
            return
        self.worker.set_fence(enabled, radius_m)
        self.show_transient_status("Geofence ayari gonderiliyor...", 2000)

    def on_rtl_alt_changed(self, alt_m: float):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: RTL irtifasi gonderilemedi", 3000, success=False)
            return
        # NOT: ArduPilot 4.7 (Ocak 2026) bu ayari RTL_ALT_M (metre) adiyla tutar; daha
        # eski surumlerde ad RTL_ALT ve birim SANTIMETREDIR. Yalnizca birine
        # yazmak, digerini calistiran FC'de ayarin sessizce kaybolmasina yol
        # aciyordu - worker artik iki adi da kendi biriminde yaziyor.
        self.worker.set_rtl_altitude(alt_m)
        self.event_log_panel.add_event(f"RTL irtifasi ayarlandi: {alt_m:.0f} m", success=True)
        self.show_transient_status("RTL irtifasi gonderiliyor...", 2000)

    def on_battery_fs_changed(self, enabled: bool, volt: float):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: pil failsafe ayari gonderilemedi", 3000, success=False)
            return
        self.worker.set_param("FS_BATT_ENABLE", 1.0 if enabled else 0.0, 9)
        self.worker.set_param("BATT_LOW_VOLT", volt, 9)
        self.event_log_panel.add_event(
            f"Pil failsafe ayarlandi: {'Aktif' if enabled else 'Kapali'}, esik {volt:.1f}V", success=True
        )
        self.show_transient_status("Pil failsafe ayari gonderiliyor...", 2000)

    def on_polygon_draw_toggled(self, enabled: bool):
        self.polygon_edit_active = enabled
        self.map_widget.set_fence_editing_mode(enabled)
        if enabled and self.guided_click_active:
            self.guided_click_active = False
            self.btn_guided_click.setChecked(False)
            self.btn_guided_click.setText("TIKLA VE GIT: KAPALI")
            self.btn_guided_click.setStyleSheet(
                "background-color: #313244; color: #cdd6f4; font-weight: 800; border-radius: 8px;"
            )
            self.map_widget.set_guided_click_mode(False)
            self.map_widget.clear_guided_target()
        if enabled:
            self.show_transient_status("Poligon cizim modu ACIK: haritaya tiklayarak nokta ekleyin", 3000)

    def on_fence_point_added(self, lat: float, lon: float):
        if not self.polygon_edit_active:
            return
        self.fence_polygon_points.append((lat, lon))
        self.safety_panel.set_polygon_point_count(len(self.fence_polygon_points))
        self.map_widget.draw_fence_edit_progress(self.fence_polygon_points)

    def on_polygon_undo_requested(self):
        if self.fence_polygon_points:
            self.fence_polygon_points.pop()
            self.safety_panel.set_polygon_point_count(len(self.fence_polygon_points))
            self.map_widget.draw_fence_edit_progress(self.fence_polygon_points)

    def on_polygon_clear_requested(self):
        self.fence_polygon_points = []
        self.safety_panel.set_polygon_point_count(0)
        self.map_widget.clear_fence_edit()
        self.map_widget.clear_fence_polygon()
        if self.worker and self.connected:
            reply = QMessageBox.question(
                self,
                "Poligon Fence Sil",
                "FC'deki poligon fence de silinsin mi?\n"
                "(Hayir derseniz sadece haritadaki gorunum temizlenir, FC'deki kayit kalir.)",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.worker.clear_fence_polygon()
                self.show_transient_status("Poligon fence siliniyor...", 0)

    def on_polygon_upload_requested(self):
        if len(self.fence_polygon_points) < 3:
            self.show_transient_status("En az 3 nokta gerekli", 3000, success=False)
            return
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: poligon gonderilemedi", 3000, success=False)
            return
        reply = QMessageBox.question(
            self,
            "Poligon Fence Yukle",
            f"{len(self.fence_polygon_points)} noktali poligon FC'ye yuklensin mi?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.worker.upload_fence_polygon(list(self.fence_polygon_points))
        self.show_transient_status("Poligon yukleniyor...", 0)

    def on_fence_polygon_upload_result(self, success: bool, message: str):
        self.event_log_panel.add_event(f"Poligon fence: {message}", success=success)
        self.show_transient_status(message, 4000, success=success)
        if success:
            self.map_widget.draw_fence_polygon(self.fence_polygon_points)
            self.map_widget.clear_fence_edit()
            # KRITIK: Poligon FC'ye yuklenmis olmasi, otopilotun ONA GORE
            # kontrol yapacagi anlamina GELMEZ. FENCE_TYPE bit maskesinde
            # "poligon" biti (deger 4) acik olmali, aksi halde FC poligonu
            # tamamen yok sayar. Yukleme basarili olunca bu biti otomatik
            # kontrol edip gerekiyorsa acacagiz.
            self._fence_type_pending_polygon_fix = True
            self.worker.request_single_param("FENCE_TYPE")

    def on_polygon_download_requested(self):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: poligon indirilemedi", 3000, success=False)
            return
        self.worker.download_fence_polygon()
        self.show_transient_status("Poligon indiriliyor...", 0)

    def on_fence_polygon_download_result(self, success: bool, message: str, points):
        self.event_log_panel.add_event(f"Poligon fence: {message}", success=success)
        self.show_transient_status(message, 4000, success=success)
        if success and points:
            self.fence_polygon_points = points
            self.safety_panel.set_polygon_point_count(len(points))
            self.map_widget.draw_fence_polygon(points)

    def on_fence_polygon_clear_result(self, success: bool, message: str):
        self.event_log_panel.add_event(f"Poligon fence: {message}", success=success)
        self.show_transient_status(message, 4000, success=success)
    def on_tab_changed(self, index):
        tab_text = self.tabs.tabText(index)
        self.map_widget.set_mission_editing(tab_text == "Ucus Plani")

    # Her modda hangi istatistik kartlarinin GIZLENECEGINI tanimlar.
    MISSION_MODE_HIDDEN_CARDS = {
        "Arama Kurtarma": {"card_wp", "card_wp_dist"},
        "Haritalama": {"card_home_dist"},
    }

    # Her modda sekmelerin hangi SIRAYLA gosterilecegini tanimlar.
    MISSION_MODE_TAB_ORDER = {
        "Standart": ["Telemetri ve Kontrol", "Ucus Plani", "Guvenlik", "Olay Gunlugu", "Ucus Tekrari"],
        "Arama Kurtarma": ["Guvenlik", "Ucus Plani", "Telemetri ve Kontrol", "Olay Gunlugu", "Ucus Tekrari"],
        "Haritalama": ["Ucus Tekrari", "Telemetri ve Kontrol", "Ucus Plani", "Guvenlik", "Olay Gunlugu"],
    }

    # Her modun sekme vurgu rengini tanimlar (mission_mode_selector.py'deki
    # renklerle ayni).
    MISSION_MODE_ACCENT = {
        "Standart": "#89dceb",
        "Arama Kurtarma": "#f38ba8",
        "Haritalama": "#f9e2af",
    }

    def _apply_tab_order(self, order, animate=True):
        """Sekmeleri verilen sirada yeniden diz. Widget'lar silinmez,
        sadece QTabWidget'tan cikarilip yeniden eklenir - ic durumlari
        (mission_panel, safety_panel vb.) korunur.

        Mod degistiginde her zaman o modun ONCELIKLI (ilk siradaki)
        sekmesine gecilir - kullanicinin bir onceki modda hangi sekmede
        oldugu ONEMLI DEGIL, cunku sekme sirasinin amaci zaten o modun
        en onemli panelini one cikarmaktir."""
        while self.tabs.count():
            self.tabs.removeTab(0)
        for label in order:
            widget = self._tab_pages[label]
            self.tabs.addTab(widget, label)
        self.tabs.setCurrentIndex(0)
        if animate:
            self._fade_in_tabs()

    def _fade_in_tabs(self):
        """Sekme icerigine kisa bir yumusak belirme (fade-in) animasyonu
        uygular - mod degisimini gorsel olarak hissettirir."""
        effect = QGraphicsOpacityEffect(self.tabs)
        self.tabs.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._tab_fade_anim = anim  # referansi sakla, cop toplayici silmesin

    def _apply_mode_accent(self, mode_name: str):
        """Secili moda gore sekme vurgu rengini degistirir."""
        color = self.MISSION_MODE_ACCENT.get(mode_name, "#89dceb")
        self.tabs.setStyleSheet(f"""
            QTabBar::tab:selected {{
                background: #313244;
                color: {color};
                border-bottom: 2px solid {color};
            }}
        """)

    def on_mission_mode_changed(self, mode_name: str):
        self.mission_mode = mode_name
        hidden = self.MISSION_MODE_HIDDEN_CARDS.get(mode_name, set())
        all_cards = (
            "card_alt", "card_gs", "card_hdg", "card_bat",
            "card_gps", "card_wp", "card_wp_dist", "card_home_dist",
        )
        for name in all_cards:
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(name not in hidden)
        order = self.MISSION_MODE_TAB_ORDER.get(mode_name, self.MISSION_MODE_TAB_ORDER["Standart"])
        self._apply_tab_order(order, animate=True)
        self._apply_mode_accent(mode_name)
        self.event_log_panel.add_event(f"Gorev modu: {mode_name}", success=None)
    def on_waypoints_changed(self, waypoints):
        self.map_widget.redraw_waypoints(waypoints)
        if not self._ignore_wp_dirty:
            self.mission_on_vehicle = False
        self._update_action_buttons()
        self._refresh_nav_cards()

    def on_mission_upload_requested(self, waypoints):
        self.worker.upload_mission(waypoints)

    def on_mission_download_requested(self):
        self.worker.download_mission()

    def show_transient_status(self, message: str, timeout_ms: int = 3000, success=None):
        bar = self.statusBar()
        if success is True:
            color = "#a6e3a1"
        elif success is False:
            color = "#f38ba8"
        else:
            color = "#cdd6f4"
        lower = message.lower()
        if "yukleniyor" in lower or message.rstrip().endswith("..."):
            timeout_ms = 0
        bar.setStyleSheet(
            f"QStatusBar {{ background-color: #181825; color: {color}; "
            f"border-top: 1px solid #313244; font-weight: 600; padding: 4px 10px; }}"
        )
        bar.showMessage(message, timeout_ms)
        self.event_log_panel.add_event(message, success=success)

    def on_mission_upload_result(self, success: bool, message: str):
        self.mission_on_vehicle = bool(success)
        prefix = "Yuklendi" if success else "Hata"
        self.show_transient_status(f"{prefix}: {message}", 3000, success=success)
        self._update_action_buttons()

    def on_mission_download_result(self, success: bool, message: str, waypoints):
        if success:
            self._ignore_wp_dirty = True
            self.mission_panel.set_waypoints(waypoints)
            self._ignore_wp_dirty = False
            self.mission_on_vehicle = True
        self.show_transient_status(
            ("Yuklendi: " if success else "Hata: ") + message,
            3000,
            success=success,
        )
        self._update_action_buttons()

    def on_mission_clear_requested(self):
        """MissionPanel'deki 'Gorevi Drondan Sil' butonu tetiklendi.
        Yerel liste MissionPanel tarafindan zaten temizlendi (bu da
        redraw_waypoints([]) uzerinden turuncu gorev cizgisini siler);
        burada ayrica dronun mavi ucus izini de temizliyoruz ve FC'nin
        gorev hafizasini silmesini istiyoruz."""
        self.mission_on_vehicle = False
        self.map_widget.clear_flight_path()
        self._update_action_buttons()
        if not self.worker or not self.connected:
            self.show_transient_status(
                "Baglanti yok: yerel liste temizlendi ama dron hafizasi silinemedi",
                3000,
                success=False,
            )
            return
        self.worker.clear_mission()

    def on_mission_clear_result(self, success: bool, message: str):
        self.show_transient_status(
            ("Temizlendi: " if success else "Hata: ") + message,
            3000,
            success=success,
        )
        self._update_action_buttons()

    def on_wizard_status(self, message: str, running: bool):
        self.wizard_running = running
        success = None
        if not running:
            success = (not message.lower().startswith("hata"))
        timeout = 0 if running else 4000
        self.show_transient_status(message, timeout, success=success)
        self._update_action_buttons()

    def update_connection_status(self, success: bool, message: str):
        self.connected = success
        if success:
            # _was_ever_connected'i asagida kullanacagimiz icin ONCE oku:
            # ilk baglantida "geri geldi" anonsu yapilmamali.
            ilk_baglanti = not self._was_ever_connected
            self._was_ever_connected = True
            self._stop_connection_alarm()
            self._style_badge(
                self.badge_connection,
                f"{self._connection_badge_prefix()} · BAGLI",
                "#a6e3a1",
            )
            self._style_reconnect_button(attention=False)
            self.show_transient_status("MAVLink baglantisi kuruldu", 3000, success=True)
            if not ilk_baglanti:
                self.voice.say(
                    "Telemetri baglantisi geri geldi",
                    key="baglanti", min_interval_s=15,
                )
            self.worker.request_fence()
            self.worker.enqueue(cmd="request_failsafe_params")
            if self._pending_mission_clear_on_connect:
                # Yeniden baglanildiginda onceki oturumdan kalma eski
                # gorevin FC'de asili kalmamasi icin otomatik temizle.
                self._pending_mission_clear_on_connect = False
                self.worker.clear_mission()
        else:
            self._style_badge(
                self.badge_connection,
                f"{self._connection_badge_prefix()} · HATA",
                "#f38ba8",
            )
            self._style_reconnect_button(attention=True)
            self.show_transient_status(f"Baglanti hatasi: {message}", 3000, success=False)
            print(f"Baglanti hatasi: {message}")
            if self._was_ever_connected:
                self.voice.say(
                    "Telemetri baglantisi kesildi",
                    key="baglanti", min_interval_s=15,
                )
            self._was_armed = False
            self.is_armed = False
            if self._was_ever_connected:
                self._start_connection_alarm()
        self._update_action_buttons()

    def update_telemetry_ui(self, data):
        if getattr(self, "is_replaying", False):
            return
        msg_type = data.get("type")

        if msg_type == "HEARTBEAT":
            armed = bool(data.get("armed"))
            self.is_armed = armed
            just_armed = armed and not self._was_armed
            just_disarmed = (not armed) and self._was_armed
            self._was_armed = armed

            flight_summary_duration = None

            if just_armed:
                self.flight_logger.stop()
                self.flight_logger.start(custom_name=self.flight_name_input.text())
                self.event_log_panel.add_event("Drone ARM edildi — ucus kaydi basladi", success=True)
                self.voice.say("Motorlar armed", key="arm", min_interval_s=3)
                self.replay_panel.refresh_file_list()
                self._start_flight_timer()
                self._flight_max_alt = None
                self._flight_max_speed = None
                self._flight_min_battery = None
                self._flight_distance_m = 0.0
                self._flight_last_pos = None
                self._flight_mode_changes = 0
                self._flight_last_mode = data.get("mode") or "--"
                self._flight_min_satellites = None
                self._flight_fence_breach = False
                self._flight_start_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif just_disarmed:
                had_flight = self._flight_start_ts is not None
                self.flight_logger.stop()
                self.event_log_panel.add_event("Drone DISARM edildi — ucus kaydi durdu", success=None)
                self.voice.say("Motorlar disarmed", key="disarm", min_interval_s=3)
                self.replay_panel.refresh_file_list()
                if had_flight:
                    flight_summary_duration = self._stop_flight_timer()

            self.safety_panel.set_armed(armed)
            if self.calibration_dialog is not None:
                self.calibration_dialog.set_armed(armed)
            if armed:
                self._style_badge(self.badge_arm, "ARMED", "#a6e3a1")
                self.btn_arm.setText("DISARM")
                self.btn_arm.setStyleSheet(
                    "background-color: #a6e3a1; color: #1e1e2e; font-weight: 800; padding: 10px; border-radius: 8px;"
                )
            else:
                self._style_badge(self.badge_arm, "DISARMED", "#f38ba8")
                self.btn_arm.setText("ARM")
                self.btn_arm.setStyleSheet(
                    "background-color: #f38ba8; color: #1e1e2e; font-weight: 800; padding: 10px; border-radius: 8px;"
                )
            mode = data.get("mode") or "--"
            self.current_mode = mode
            if self.is_armed:
                if self._flight_last_mode is not None and mode != self._flight_last_mode:
                    self._flight_mode_changes += 1
                self._flight_last_mode = mode
            self._style_badge(self.badge_mode, f"MOD: {mode}", "#89b4fa")
            self._update_action_buttons()

            if flight_summary_duration is not None:
                self._capture_flight_summary(flight_summary_duration)
        elif msg_type == "ATTITUDE":
            self.lbl_pitch.setText(f"Pitch: {data['pitch']:.3f} rad")
            self.lbl_roll.setText(f"Roll: {data['roll']:.3f} rad")
            self.lbl_yaw.setText(f"Yaw: {data['yaw']:.3f} rad")
            heading_degrees = (math.degrees(data["yaw"]) + 360) % 360
            self.map_widget.update_heading(heading_degrees)
            self.artificial_horizon.set_attitude(data["pitch"], data["roll"])

        elif msg_type == "GLOBAL_POSITION_INT":
            self.lbl_lat.setText(f"Enlem: {data['lat']:.6f}°")
            self.lbl_lon.setText(f"Boylam: {data['lon']:.6f}°")
            self.card_alt.set_value(f"{data['alt']:.1f}")
            self.current_lat = data["lat"]
            self.current_lon = data["lon"]
            self.current_alt = data["alt"]
            self.map_widget.update_position(data["lat"], data["lon"])
            self._refresh_nav_cards()
            if self.is_armed:
                if self._flight_max_alt is None or self.current_alt > self._flight_max_alt:
                    self._flight_max_alt = self.current_alt
                if self._flight_last_pos is not None:
                    self._flight_distance_m += haversine_m(
                        self._flight_last_pos[0], self._flight_last_pos[1],
                        self.current_lat, self.current_lon,
                    )
                self._flight_last_pos = (self.current_lat, self.current_lon)
            self.flight_logger.log_row(
                lat=self.current_lat,
                lon=self.current_lon,
                alt=self.current_alt,
                groundspeed=self.current_groundspeed,
                heading=self.current_heading,
                battery=self.current_battery,
                mode=self.current_mode,
                armed=self.is_armed,
            )

        elif msg_type == "VFR_HUD":
            self.card_gs.set_value(f"{data['groundspeed']:.1f}")
            self.current_groundspeed = data["groundspeed"]
            if self.is_armed and (
                self._flight_max_speed is None or self.current_groundspeed > self._flight_max_speed
            ):
                self._flight_max_speed = self.current_groundspeed
            self.current_heading = data["heading"]
            self.card_hdg.set_value(f"{int(data['heading']):03d}")
            self.map_widget.update_heading(float(data["heading"]))
            # NOT: VFR_HUD.alt MSL (deniz seviyesinden mutlak) irtifadir,
            # GLOBAL_POSITION_INT.alt ise kalkis noktasina gore relative_alt.
            # card_alt kullanicinin bildigi "kalkistan bu yana yukseklik"
            # degeridir; ikisini ayni karta yazmak degerin surekli 30m ile
            # 585m arasinda sicramasina (yanip sonme hissi) neden oluyordu.
            # Bu yuzden card_alt SADECE GLOBAL_POSITION_INT'ten guncellenir.

        elif msg_type == "SYS_STATUS":
            self.safety_panel.process_sys_status(data)
            remaining = data.get("battery_remaining", -1)
            self.current_battery = remaining
            if self.is_armed and remaining is not None and remaining >= 0:
                if self._flight_min_battery is None or remaining < self._flight_min_battery:
                    self._flight_min_battery = remaining
            if remaining is None or remaining < 0:
                self.card_bat.set_value("--")
                self.card_bat.set_accent("#a6e3a1")
            else:
                self.card_bat.set_value(str(int(remaining)))
                if remaining <= 20:
                    self.card_bat.set_accent("#f38ba8")
                    if not self._low_battery_warned:
                        self._low_battery_warned = True
                        self.event_log_panel.add_event(
                            f"DUSUK PIL UYARISI: %{int(remaining)}", success=False
                        )
                        self.show_transient_status(
                            f"DUSUK PIL: %{int(remaining)} — inis/RTL dusunun", 5000, success=False
                        )
                    # Uyari ekranda bir kez cikar, ancak pil kritik
                    # kaldigi surece 30 saniyede bir sesli tekrarlanir.
                    self.voice.say(
                        f"Dusuk pil, yuzde {int(remaining)}",
                        key="dusuk_pil", min_interval_s=30,
                    )
                elif remaining <= 40:
                    self.card_bat.set_accent("#f9e2af")
                    self._low_battery_warned = False
                else:
                    self.card_bat.set_accent("#a6e3a1")
                    self._low_battery_warned = False

        elif msg_type == "GPS_RAW_INT":
            sats = data.get("satellites_visible", 0)
            self.current_satellites = int(sats)
            self.card_gps.set_value(str(int(sats)))
            if self.is_armed and (
                self._flight_min_satellites is None or int(sats) < self._flight_min_satellites
            ):
                self._flight_min_satellites = int(sats)
            if sats < 6:
                self.card_gps.set_accent("#f38ba8")
            elif sats < 10:
                self.card_gps.set_accent("#f9e2af")
            else:
                self.card_gps.set_accent("#cba6f7")

        elif msg_type == "RADIO_STATUS":
            # Yerel ve uzak ucun DUSUK olani baglantinin gercek kalitesini
            # belirler; zayif yon hangisiyse onu gosteriyoruz.
            pct = min(int(data.get("rssi_pct", 0)), int(data.get("remrssi_pct", 0)))
            self.current_rssi = pct
            self.card_rssi.set_value(str(pct))
            if pct < 30:
                self.card_rssi.set_accent("#f38ba8")
            elif pct < 60:
                self.card_rssi.set_accent("#f9e2af")
            else:
                self.card_rssi.set_accent("#94e2d5")

        elif msg_type == "MISSION_CURRENT":
            self.mission_current_seq = int(data.get("seq", 0))
            self._refresh_nav_cards()

        elif msg_type == "HOME_POSITION":
            self.home_lat = data["lat"]
            self.home_lon = data["lon"]
            self.map_widget.update_home(data["lat"], data["lon"])
            # .waypoints disa aktarmasinda 0. satir (home) icin
            self.mission_panel.set_home(data["lat"], data["lon"])
            self._refresh_nav_cards()
            self._refresh_geofence()

        elif msg_type == "PARAM_VALUE":
            pid = data["param_id"]
            if pid == "FENCE_ENABLE":
                self.fence_enabled = bool(data["value"])
                self._refresh_geofence()
            elif pid == "FENCE_RADIUS":
                self.fence_radius = data["value"]
                self._refresh_geofence()
            elif pid in ("RTL_ALT_M", "RTL_ALT"):
                # RTL_ALT_M metre, eski RTL_ALT santimetre cinsindedir;
                # panel her zaman metre bekler.
                alt_m = data["value"] if pid == "RTL_ALT_M" else data["value"] / 100.0
                self.safety_panel.set_failsafe_display(alt_m, None, None)
            elif pid == "FS_BATT_ENABLE":
                self.batt_fs_enabled = bool(data["value"])
                self.safety_panel.set_failsafe_display(None, self.batt_fs_enabled, None)
            elif pid == "BATT_LOW_VOLT":
                self.batt_fs_volt = data["value"]
                self.safety_panel.set_failsafe_display(None, None, self.batt_fs_volt)
            elif pid == "FENCE_TYPE":
                fence_type_val = int(data["value"])
                if self._fence_type_pending_polygon_fix:
                    self._fence_type_pending_polygon_fix = False
                    if not (fence_type_val & 4):
                        new_val = fence_type_val | 4
                        self.worker.set_param("FENCE_TYPE", float(new_val), data["param_type"])
                        self.event_log_panel.add_event(
                            f"FENCE_TYPE guncellendi: poligon turu aktif edildi "
                            f"({fence_type_val} -> {new_val})",
                            success=True,
                        )
                    else:
                        self.event_log_panel.add_event(
                            "FENCE_TYPE zaten poligon turunu iceriyor", success=True
                        )                
            if self.param_editor_dialog is not None:
                self.param_editor_dialog.on_param_received(data)
        elif msg_type == "ACCEL_CAL_POSITION":
            if self.calibration_dialog is not None:
                self.calibration_dialog.on_accel_position_request(data)

        elif msg_type == "MAG_CAL_PROGRESS":
            if self.calibration_dialog is not None:
                self.calibration_dialog.on_mag_progress(data)

        elif msg_type == "MAG_CAL_REPORT":
            if self.calibration_dialog is not None:
                self.calibration_dialog.on_mag_report(data)

        elif msg_type == "EKF_STATUS_REPORT":
            self.safety_panel.process_ekf_status(data)

        elif msg_type == "STATUSTEXT":
            self.safety_panel.process_statustext(data)
            if self.calibration_dialog is not None:
                self.calibration_dialog.on_statustext(data)
            text_lower = (data.get("text") or "").lower()
            if "fence" in text_lower:
                self.event_log_panel.add_event(data.get("text", ""), success=False)
                self.voice.say(
                    "Geofence ihlali", key="fence", min_interval_s=20
                )
            if self.is_armed and "breach" in text_lower:
                self._flight_fence_breach = True
            # MAV_SEVERITY: 0 EMERGENCY ... 3 ERROR. Bu esigin altindaki
            # mesajlar (uyari/bilgi) sesli okunmaz, yoksa surekli konusur.
            if int(data.get("severity", 6)) <= 3:
                self.voice.say(
                    data.get("text", ""),
                    key=f"kritik:{text_lower[:24]}", min_interval_s=20,
                )
    def on_preflight_check_clicked(self):
        checks = []

        checks.append((
            "Baglanti", self.connected,
            "Bagli" if self.connected else "Bagli degil", True,
        ))

        if self.current_satellites is None:
            checks.append(("GPS Kilidi", None, "Veri yok", True))
        else:
            ok = self.current_satellites >= 6
            checks.append(("GPS Kilidi", ok, f"{self.current_satellites} uydu", True))

        if self.current_battery is None or self.current_battery < 0:
            checks.append(("Batarya", None, "Veri yok", True))
        else:
            ok = self.current_battery > 20
            checks.append(("Batarya", ok, f"%{int(self.current_battery)}", True))

        ekf_ok = self.safety_panel.get_ekf_ok()
        checks.append((
            "EKF Durumu", ekf_ok,
            "Saglikli" if ekf_ok else ("Sorunlu" if ekf_ok is False else "Veri yok"), True,
        ))

        issue_count = self.safety_panel.get_active_issue_count()
        checks.append((
            "Aktif PreArm Uyarilari", issue_count == 0,
            "Yok" if issue_count == 0 else f"{issue_count} sorun", True,
        ))

        fence_detail = (
            f"Aktif, {self.fence_radius:.0f} m" if self.fence_enabled and self.fence_radius
            else "Kapali"
        )
        checks.append(("Geofence", bool(self.fence_enabled), fence_detail, False))

        wp_count = len(self.mission_panel.waypoints)
        checks.append((
            "Gorev Yuklu", self.mission_on_vehicle and wp_count > 0,
            f"{wp_count} waypoint" if wp_count else "Waypoint yok", False,
        ))

        required_ok = all(status for (_, status, _, required) in checks if required)

        dialog = PreflightChecklistDialog(checks, required_ok, parent=self)
        dialog.exec_()
    def on_arm_disarm_clicked(self):
        action_text = "DISARM" if self.is_armed else "ARM"
        reply = QMessageBox.question(
            self,
            "Onay",
            f"Drone'u {action_text} etmek istediginizden emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.worker.arm_disarm(not self.is_armed)

    def on_set_mode_clicked(self):
        self.worker.change_mode(self.mode_combo.currentText())

    def on_rtl_clicked(self):
        reply = QMessageBox.question(
            self,
            "RTL Onayi",
            "Return to Launch (RTL) moduna gecilsin mi?\nDrone otomatik olarak eve donecek.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.worker.change_mode("RTL")

    def on_land_clicked(self):
        reply = QMessageBox.question(
            self,
            "Inis Onayi",
            "Drone bulundugu konumda inise gecirilsin mi?\nBu islem geri alinamaz.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.worker.change_mode("LAND")
    def on_takeoff_clicked(self):
        alt = int(self.spin_takeoff_alt.value())
        reply = QMessageBox.question(
            self,
            "Kalkis",
            f"GUIDED TAKEOFF ile {alt} m irtifaya cikilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.show_transient_status("Kalkis komutu gonderiliyor...", 0)
        self.worker.takeoff(alt)

    def on_fly_mission_clicked(self):
        alt = int(self.spin_takeoff_alt.value())
        n = len(self.mission_panel.waypoints)

        reply = QMessageBox.question(
            self,
            "Gorevi Ucur",
            (
                f"Sira: ARM → GUIDED → TAKEOFF ({alt} m) → AUTO\n"
                f"{n} waypoint yuklu gorev baslatilacak. Devam?"
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.wizard_running = True
        self._update_action_buttons()
        self.worker.fly_mission(alt)

    def on_guided_click_toggled(self):
        self.guided_click_active = self.btn_guided_click.isChecked()
        self.map_widget.set_guided_click_mode(self.guided_click_active)
        if self.guided_click_active:
            if self.polygon_edit_active:
                self.polygon_edit_active = False
                self.safety_panel.set_polygon_button_checked(False)
                self.map_widget.set_fence_editing_mode(False)
            self.btn_guided_click.setText("TIKLA VE GIT: ACIK")
            self.btn_guided_click.setStyleSheet(
                "background-color: #a6e3a1; color: #1e1e2e; font-weight: 800; border-radius: 8px;"
            )
            self.show_transient_status(
                "Tikla ve Git ACIK: haritaya tikladiginiz nokta drone'a aninda gonderilir", 3000
            )
        else:
            self.btn_guided_click.setText("TIKLA VE GIT: KAPALI")
            self.btn_guided_click.setStyleSheet(
                "background-color: #313244; color: #cdd6f4; font-weight: 800; border-radius: 8px;"
            )
            self.map_widget.clear_guided_target()

    def on_guided_goto_requested(self, lat: float, lon: float):
        if not self.connected:
            self.show_transient_status("Baglanti yok: komut gonderilemedi", 3000, success=False)
            return
        alt = int(self.spin_takeoff_alt.value())
        reply = QMessageBox.question(
            self,
            "Tikla ve Git",
            f"Drone su noktaya GUIDED modda gonderilsin mi?\n\n"
            f"Enlem: {lat:.6f}\nBoylam: {lon:.6f}\nIrtifa: {alt} m",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.worker.goto_position(lat, lon, alt)
        self.map_widget.show_guided_target(lat, lon)
        self.show_transient_status("Hedef gonderiliyor...", 0)

    def on_param_editor_clicked(self):
        if self.param_editor_dialog is not None:
            self.param_editor_dialog.raise_()
            self.param_editor_dialog.activateWindow()
            return
        dialog = ParameterEditorDialog(parent=self)
        dialog.request_download.connect(self._on_param_download_requested)
        dialog.apply_param.connect(self._on_param_apply_requested)
        dialog.finished.connect(self._on_param_dialog_closed)
        self.param_editor_dialog = dialog
        dialog.show()
        self._on_param_download_requested()

    def _refresh_voice_button(self):
        if not self.voice.available:
            self.btn_voice.setText("SES: YOK")
            self.btn_voice.setEnabled(False)
            self.btn_voice.setToolTip(
                "Bu sistemde metin okuma araci bulunamadi "
                "(macOS: say · Linux: spd-say/espeak · Windows: PowerShell)"
            )
            return
        acik = self.voice.enabled
        self.btn_voice.setText("SES: ACIK" if acik else "SES: KAPALI")
        self.btn_voice.setToolTip(
            "Kritik uyarilarin sesli anonsunu ac/kapat"
        )
        self.btn_voice.setStyleSheet(
            "background-color: %s; color: #1e1e2e; font-weight: 800; "
            "border-radius: 8px; padding: 8px 12px;"
            % ("#a6e3a1" if acik else "#45475a")
        )

    def on_voice_toggle_clicked(self):
        acik = self.voice.set_enabled(not self.voice.enabled)
        self._refresh_voice_button()
        self.event_log_panel.add_event(
            f"Sesli uyarilar {'acildi' if acik else 'kapatildi'}", success=acik
        )
        if acik:
            self.voice.say("Sesli uyarilar acik", key="ses_test", min_interval_s=0)

    def on_calibration_clicked(self):
        """Kalibrasyon sihirbazini acar. Pencere MAVLink'e dogrudan
        dokunmaz; sinyalleri buradan worker'in komut kuyruguna aktarilir."""
        if self.calibration_dialog is not None:
            self.calibration_dialog.raise_()
            self.calibration_dialog.activateWindow()
            return
        dialog = CalibrationDialog(armed=self.is_armed, parent=self)
        dialog.start_mag_requested.connect(
            lambda: self._kalibrasyon_komutu("start_mag_cal", "Pusula kalibrasyonu baslatildi")
        )
        dialog.accept_mag_requested.connect(
            lambda: self._kalibrasyon_komutu("accept_mag_cal", "Pusula kalibrasyonu kaydedildi")
        )
        dialog.cancel_mag_requested.connect(
            lambda: self._kalibrasyon_komutu("cancel_mag_cal", "Pusula kalibrasyonu iptal edildi")
        )
        dialog.start_accel_requested.connect(
            lambda: self._kalibrasyon_komutu("start_accel_cal", "Ivmeolcer kalibrasyonu baslatildi")
        )
        dialog.accel_position_confirmed.connect(self._on_accel_position_confirmed)
        dialog.start_level_requested.connect(
            lambda: self._kalibrasyon_komutu("start_level_cal", "Yatay duzlem kalibrasyonu baslatildi")
        )
        dialog.start_gyro_requested.connect(
            lambda: self._kalibrasyon_komutu("start_gyro_cal", "Jiroskop kalibrasyonu baslatildi")
        )
        dialog.start_baro_requested.connect(
            lambda: self._kalibrasyon_komutu("start_baro_cal", "Barometre kalibrasyonu baslatildi")
        )
        dialog.finished.connect(self._on_calibration_dialog_closed)
        self.calibration_dialog = dialog
        dialog.show()

    def _kalibrasyon_komutu(self, komut: str, olay_metni: str):
        """Sihirbaz sinyallerini worker komutuna cevirir. Kalibrasyon
        yalnizca DISARM haldeyken ve baglanti varken gonderilir."""
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: kalibrasyon gonderilemedi", 3000, success=False)
            return
        if self.is_armed:
            self.show_transient_status(
                "Arac ARM durumda: once DISARM edin", 4000, success=False
            )
            return
        self.worker.enqueue(cmd=komut)
        self.event_log_panel.add_event(olay_metni, success=True)
        self.show_transient_status(olay_metni, 3000)

    def _on_accel_position_confirmed(self, position: int):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: pozisyon gonderilemedi", 3000, success=False)
            return
        self.worker.send_accel_cal_position(position)

    def _on_calibration_dialog_closed(self):
        self.calibration_dialog = None

    def _on_param_download_requested(self):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: parametreler indirilemedi", 3000, success=False)
            return
        self.worker.request_all_params()
        self.show_transient_status("Parametreler indiriliyor...", 3000)

    def _on_param_apply_requested(self, name: str, value: float, param_type: int):
        if not self.worker or not self.connected:
            self.show_transient_status("Baglanti yok: parametre yazilamadi", 3000, success=False)
            return
        self.worker.set_param(name, value, param_type)
        self.event_log_panel.add_event(f"Parametre yazildi: {name} = {value}", success=True)
        self.show_transient_status(f"Yazildi: {name} = {value}", 3000, success=True)

    def _on_param_dialog_closed(self):
        self.param_editor_dialog = None
    def on_replay_state_changed(self, active: bool):
        self.is_replaying = active

    def on_replay_sample(self, data: dict):
        lat = data["lat"]
        lon = data["lon"]
        alt = data["alt"]
        groundspeed = data["groundspeed"]
        heading = data["heading"]
        battery = data["battery"]
        mode = data["mode"]

        self.card_alt.set_value(f"{alt:.1f}")
        self.card_gs.set_value(f"{groundspeed:.1f}")
        self.card_hdg.set_value(f"{int(heading):03d}")
        try:
            self.card_bat.set_value(f"{float(battery):.0f}")
        except (ValueError, TypeError):
            pass
        self.lbl_lat.setText(f"Enlem: {lat:.6f}\u00b0")
        self.lbl_lon.setText(f"Boylam: {lon:.6f}\u00b0")

        self.map_widget.update_position(lat, lon)
        self.map_widget.update_heading(heading)


    def on_arm_result(self, success: bool, message: str):
        self.event_log_panel.add_event(message, success=success)
        if not success:
            self.show_transient_status(message, 8000, success=False)
            # ARM reddi sessizce gecilmemeli: sebebi (PreArm mesaji dahil)
            # ayri bir pencerede de goster.
            QMessageBox.warning(
                self,
                "ARM basarisiz",
                f"{message}\n\nAyrintili PreArm uyarilari icin Guvenlik "
                f"sekmesine bakin.",
            )

    def on_goto_result(self, success: bool, message: str):
        self.event_log_panel.add_event(f"Tikla ve Git: {message}", success=success)
        self.show_transient_status(message, 4000, success=success)       
    def on_connection_settings_clicked(self):
        dialog = ConnectionDialog(self.connection_string, self)
        if dialog.exec_() == dialog.Accepted:
            new_connection_string = dialog.get_connection_string()
            if new_connection_string:
                self.connection_string = new_connection_string
                self.event_log_panel.add_event(
                    f"Baglanti ayarlari degistirildi: {new_connection_string}", success=None
                )
                self.on_reconnect_clicked()
    def on_reconnect_clicked(self):
        self.safety_panel.reset_connection_state()
        self.show_transient_status("Yeniden baglaniliyor...", 0)
        self._style_reconnect_button(attention=False)
        old = self.worker
        self._disconnect_worker(old)
        if old is not None:
            old.stop()
        self.connected = False
        self.mission_on_vehicle = False
        self._was_armed = False
        self.is_armed = False
        # Eski oturumdan kalan gorev planini GCS ekraninda da temizle
        # (haritadaki eski rota ve tablo dahil); FC tarafi baglanti
        # kurulunca update_connection_status icinde otomatik temizlenecek.
        self._ignore_wp_dirty = True
        self.mission_panel.set_waypoints([], emit_changed=True)
        self._ignore_wp_dirty = False
        self.map_widget.clear_flight_path()
        self._pending_mission_clear_on_connect = True
        self._update_action_buttons()
        self._start_worker()

    def closeEvent(self, event):
        print("Pencere kapatiliyor...")
        self.voice.stop()
        if self.worker is not None:
            self._disconnect_worker(self.worker)
            self.worker.stop()
        event.accept()


def apply_dark_palette(app):
    palette = QPalette()
    bg = QColor("#1e1e2e")
    surface = QColor("#181825")
    text = QColor("#cdd6f4")
    highlight = QColor("#89b4fa")
    palette.setColor(QPalette.Window, bg)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, surface)
    palette.setColor(QPalette.AlternateBase, bg)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, QColor("#313244"))
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
    palette.setColor(QPalette.ToolTipBase, surface)
    palette.setColor(QPalette.ToolTipText, text)
    app.setPalette(palette)


if __name__ == "__main__":
    # QtWebEngine (harita) bu bayragin QApplication'dan ONCE ayarlanmasini
    # sart kosar; aksi halde "AA_ShareOpenGLContexts must be set before a
    # QCoreApplication instance is created" hatasiyla acilmaz. Gelistirmede
    # ui.map_widget_v3 importu bunu tesadufen sagliyordu, ancak paketlenmis
    # surumde import sirasi degisebildigi icin acikca ayarliyoruz.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(DARK_STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec_())
