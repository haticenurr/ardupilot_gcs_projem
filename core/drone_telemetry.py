"""
drone_telemetry.py
-------------------
MAVLink baglantisini yoneten ve telemetri / gorev komutlarini okuyan modul.

ONEMLI: Bu sinifin self.master soketine yalnizca TelemetryWorker thread'i
dokunmalidir. GUI dogrudan takeoff / download cagirmamalidir.
"""

import time

from pymavlink import mavutil

# GCS / gimbal / kamera HEARTBEAT'leri ARM bayragini tasimaz. Bunlar
# otopilot HEARTBEAT'i ile karisirsa GUI ARM olduktan hemen sonra
# sahte bir DISARM (ve ucus ozeti penceresi) gorur.
def _mav_types(*names):
    found = set()
    for name in names:
        value = getattr(mavutil.mavlink, name, None)
        if value is not None:
            found.add(int(value))
    return found


_NON_VEHICLE_HEARTBEAT_TYPES = _mav_types(
    "MAV_TYPE_GCS",
    "MAV_TYPE_GIMBAL",
    "MAV_TYPE_ADSB",
    "MAV_TYPE_ONBOARD_CONTROLLER",
    "MAV_TYPE_CAMERA",
    "MAV_TYPE_ANTENNA_TRACKER",
    "MAV_TYPE_FLARM",
)


def is_vehicle_heartbeat(msg, target_system=None):
    """Otopilot/arac HEARTBEAT'i mi? GCS ve yan birimler elenir."""
    if msg is None or msg.get_type() != "HEARTBEAT":
        return False
    if int(getattr(msg, "type", -1)) in _NON_VEHICLE_HEARTBEAT_TYPES:
        return False
    if target_system:
        try:
            if msg.get_srcSystem() != int(target_system):
                return False
        except Exception:
            return False
    return True


# Gorev tablosuna aktarilacak konumlu NAV komutlari
_NAV_COMMANDS = {
    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
    mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM,
    mavutil.mavlink.MAV_CMD_NAV_LOITER_TURNS,
    mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME,
    mavutil.mavlink.MAV_CMD_NAV_LAND,
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
    mavutil.mavlink.MAV_CMD_NAV_SPLINE_WAYPOINT,
}


# safety_panel.py'daki SENSOR_LABELS anahtarlariyla birebir eslesen,
# MAVLink SYS_STATUS bit maskesi -> okunabilir isim eslemesi.
_SENSOR_BITS = {
    "gyro": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_GYRO,
    "accel": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_ACCEL,
    "mag": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_MAG,
    "baro": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_ABSOLUTE_PRESSURE,
    "gps": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_GPS,
    "rc": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_RC_RECEIVER,
    "ahrs": mavutil.mavlink.MAV_SYS_STATUS_AHRS,
    "battery": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_BATTERY,
}
# Dairesel geofence icin okunacak FC parametreleri.
_FENCE_PARAMS = ["FENCE_ENABLE", "FENCE_RADIUS", "FENCE_ALT_MAX"]


class DroneTelemetry:
    def __init__(self, connection_string="udp:127.0.0.1:14550"):
        print(f"[DroneTelemetry] Baglanti kuruluyor: {connection_string}")
        # ConnectionDialog seri port secildiginde "PORT,BAUD" formatinda
        # bir string uretir (orn. "/dev/ttyUSB0,57600"). pymavlink'in
        # mavlink_connection() fonksiyonu bunu TEK bir cihaz adi olarak
        # yorumlar, baud rate'i AYRI bir parametre olarak bekler. Bu
        # yuzden virgul varsa (ve bu bir udp/tcp adresi degilse) ayirip
        # baud'u ayrica gecirmemiz gerekiyor.
        if "," in connection_string and not connection_string.startswith(("udp", "tcp")):
            port, _, baud_str = connection_string.partition(",")
            try:
                baud = int(baud_str.strip())
            except ValueError:
                baud = 57600
            self.master = mavutil.mavlink_connection(port.strip(), baud=baud)
        else:
            self.master = mavutil.mavlink_connection(connection_string)

        self._wait_vehicle_heartbeat(timeout=10)
        print(
            f"[DroneTelemetry] Heartbeat alindi! "
            f"(system={self.master.target_system}, "
            f"component={self.master.target_component})"
        )

        self._request_data_streams()
        self._request_home_position()

    def _wait_vehicle_heartbeat(self, timeout=10):
        """Ilk gelen HEARTBEAT GCS ise target_system yanlis kalir.
        Yalnizca arac/otopilot HEARTBEAT'ini kabul et."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            msg = self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=remaining)
            if msg is None:
                continue
            if not is_vehicle_heartbeat(msg, target_system=None):
                continue
            self.master.target_system = msg.get_srcSystem()
            self.master.target_component = msg.get_srcComponent()
            return
        raise TimeoutError("Arac HEARTBEAT'i alinamadi (zaman asimi)")

    def _request_data_streams(self):
        try:
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                4,
                1,
            )
        except Exception as e:
            print(f"[DroneTelemetry] Data stream istegi gonderilemedi: {e}")

    def _request_home_position(self):
        """FC'den HOME_POSITION mesajini talep et (MAV_CMD_GET_HOME_POSITION)."""
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_GET_HOME_POSITION,
                0,
                0, 0, 0, 0, 0, 0, 0,
            )
        except Exception as e:
            print(f"[DroneTelemetry] Home konumu istenemedi: {e}")
    def request_home_position(self):
        """Genel (public) API: home konumunu FC'den tekrar ister.
        ArduCopter home'u her ARM aninda o anki konuma sifirlar/gunceller;
        bu yuzden ilk baglantida alinan home degeri her ARM sonrasi
        eskimis olabilir. TelemetryWorker, yeni bir ARM tespit ettiginde
        bunu tekrar cagirir."""
        self._request_home_position()

    def get_telemetry_data(self):
        """
        Su mesaj turlerinden biri geldiyse dict olarak dondurur:
          - HEARTBEAT           -> armed, mode
          - ATTITUDE            -> roll, pitch, yaw
          - GLOBAL_POSITION_INT -> lat, lon, alt
          - VFR_HUD             -> groundspeed, heading, climb, throttle, alt
          - SYS_STATUS          -> battery_remaining, voltage_battery
          - GPS_RAW_INT         -> satellites_visible, fix_type
          - MISSION_CURRENT     -> seq (hedeflenen waypoint index'i)
          - HOME_POSITION       -> lat, lon, alt
        """
        msg = self.master.recv_match(
            type=[
                "HEARTBEAT",
                "ATTITUDE",
                "GLOBAL_POSITION_INT",
                "VFR_HUD",
                "SYS_STATUS",
                "GPS_RAW_INT",
                "MISSION_CURRENT",
                "HOME_POSITION",
                "EKF_STATUS_REPORT",
                "STATUSTEXT",
                "PARAM_VALUE",
            ],
            blocking=False,
        )
        if msg is None:
            return None

        msg_type = msg.get_type()

        if msg_type == "HEARTBEAT":
            if not is_vehicle_heartbeat(msg, self.master.target_system):
                return None
            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            mode_name = "UNKNOWN"
            try:
                mapping = self.master.mode_mapping()
                inverse = {v: k for k, v in mapping.items()}
                mode_name = inverse.get(msg.custom_mode, f"MODE_{msg.custom_mode}")
            except Exception:
                pass
            return {
                "type": "HEARTBEAT",
                "armed": armed,
                "mode": mode_name,
            }

        if msg_type == "ATTITUDE":
            return {
                "type": "ATTITUDE",
                "roll": msg.roll,
                "pitch": msg.pitch,
                "yaw": msg.yaw,
            }

        elif msg_type == "GLOBAL_POSITION_INT":
            lat = msg.lat / 1e7
            lon = msg.lon / 1e7
            return {
                "type": "GLOBAL_POSITION_INT",
                "lat": lat,
                "lon": lon,
                "alt": msg.relative_alt / 1000.0,
            }

        elif msg_type == "VFR_HUD":
            return {
                "type": "VFR_HUD",
                "groundspeed": msg.groundspeed,
                "heading": msg.heading,
                "climb": msg.climb,
                "throttle": msg.throttle,
                "alt": msg.alt,
            }

        elif msg_type == "SYS_STATUS":
            return {
                "type": "SYS_STATUS",
                "battery_remaining": msg.battery_remaining,
                "voltage_battery": msg.voltage_battery / 1000.0,
                "sensors": self._decode_sensor_health(msg),
            }

        elif msg_type == "EKF_STATUS_REPORT":
            return {
                "type": "EKF_STATUS_REPORT",
                "flags": int(msg.flags),
            }

        elif msg_type == "STATUSTEXT":
            text = msg.text
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore")
            text = text.rstrip("\x00").strip()
            return {
                "type": "STATUSTEXT",
                "text": text,
                "severity": int(msg.severity),
            }
        elif msg_type == "PARAM_VALUE":
            param_id = msg.param_id
            if isinstance(param_id, bytes):
                param_id = param_id.decode("utf-8", errors="ignore")
            param_id = param_id.rstrip("\x00")
            return {
                "type": "PARAM_VALUE",
                "param_id": param_id,
                "value": float(msg.param_value),
                "param_index": int(msg.param_index),
                "param_count": int(msg.param_count),
                "param_type": int(msg.param_type),
            }
        elif msg_type == "GPS_RAW_INT":
            return {
                "type": "GPS_RAW_INT",
                "satellites_visible": msg.satellites_visible,
                "fix_type": msg.fix_type,
            }

        elif msg_type == "MISSION_CURRENT":
            return {
                "type": "MISSION_CURRENT",
                "seq": int(msg.seq),
            }

        elif msg_type == "HOME_POSITION":
            lat = msg.latitude / 1e7
            lon = msg.longitude / 1e7
            return {
                "type": "HOME_POSITION",
                "lat": lat,
                "lon": lon,
                "alt": msg.altitude / 1000.0,
            }

        return None

    def send_arm_disarm(self, arm: bool):
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1 if arm else 0,
            0, 0, 0, 0, 0, 0,
        )

        msg = self.master.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)

        if msg is None:
            return False, "Zaman asimi: FC'den yanit gelmedi"

        if msg.command != mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
            return True, "Komut gonderildi (baska bir ACK ile karsilasildi)"

        if msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            action = "ARM" if arm else "DISARM"
            return True, f"{action} basarili"
        else:
            action = "ARM" if arm else "DISARM"
            return False, f"{action} reddedildi (kod: {msg.result})"

    def set_mode(self, mode_name: str):
        if mode_name not in self.master.mode_mapping():
            print(f"[DroneTelemetry] Gecersiz mod: {mode_name}")
            return False
        mode_id = self.master.mode_mapping()[mode_name]
        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id,
        )
        return True

    def takeoff(self, altitude_m: float):
        """
        MAV_CMD_NAV_TAKEOFF (22): param7 hedef irtifa (metre, relative).
        ArduCopter GUIDED + ARM sonrasi kalkis icin kullanilir.
        """
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0, 0, 0, 0, 0, 0,
            float(altitude_m),
        )

    def goto_position(self, lat: float, lon: float, altitude_m: float):
        """
        'Tikla ve Git' - MAV_CMD_DO_REPOSITION ile anlik hedef verir.
        param2 bitmask=1, drone GUIDED modda degilse bile otomatik olarak
        GUIDED'a gecirir - bu yuzden onceden GUIDED moda gecmek sart degil.
        Lat/lon COMMAND_INT uzerinden int32 (degE7) olarak gonderilir;
        COMMAND_LONG'daki float32 param'lar bu hassasiyeti tasiyamaz.
        """
        while self.master.recv_match(type="COMMAND_ACK", blocking=False) is not None:
            pass

        self.master.mav.command_int_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            mavutil.mavlink.MAV_CMD_DO_REPOSITION,
            0, 0,
            -1.0,
            1,
            0,
            float("nan"),
            int(lat * 1e7),
            int(lon * 1e7),
            float(altitude_m),
        )

        msg = self.master.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)
        if msg is None:
            return False, "Zaman asimi: FC'den yanit gelmedi"
        if msg.command != mavutil.mavlink.MAV_CMD_DO_REPOSITION:
            return True, "Komut gonderildi (baska bir ACK ile karsilasildi)"
        if msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            return True, "Hedef kabul edildi"
        result_names = {
            v: k for k, v in vars(mavutil.mavlink).items()
            if k.startswith("MAV_RESULT_")
        }
        result_text = result_names.get(msg.result, f"kod {msg.result}")
        return False, f"Hedef reddedildi: {result_text}"
    def set_current_waypoint(self, seq: int = 0):
        """
        FC uzerindeki 'su anki waypoint' (mission_current) degerini acikca
        seq'e ayarlar (MISSION_SET_CURRENT).

        Neden gerekli: ArduCopter, AUTO moduna girildiginde mission_current
        index'inden itibaren devam eder. Bu index onceki bir gorev
        denemesinden kalmis olabilir. set_mode("AUTO") + start_mission()
        bunu SIFIRLAMAZ; bu yuzden AUTO'ya gecmeden once index'i acikca
        0'a (veya istenen seq'e) cekmek gerekir.
        """
        try:
            self.master.mav.mission_set_current_send(
                self.master.target_system,
                self.master.target_component,
                seq,
            )
        except Exception as e:
            print(f"[DroneTelemetry] MISSION_SET_CURRENT gonderilemedi: {e}")

    def start_mission(self):
        """AUTO moda gecildikten sonra gorevi baslat (MAV_CMD_MISSION_START)."""
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_MISSION_START,
            0,
            0, 0, 0, 0, 0, 0, 0,
        )

    def upload_mission(self, waypoints):
        """
        NOT (onemli): ArduPilot mission protokolunde seq=0 daima 'home'
        slotudur; FC bunu gercek bir nav komutu olarak yurutmez, AUTO
        moda girildiginde otomatik atlanir. Bu yuzden gonderilen ilk
        gercek waypoint (kullanicinin tablo/haritadaki 1. noktasi)
        seq=1'e yazilmalidir, seq=0'a degil. Bunu atlarsak drone her
        zaman 2. noktadan baslar ve 1. noktaya hic ugramaz.
        """
        if not waypoints:
            return False, "Waypoint listesi bos"

        try:
            self.master.mav.mission_clear_all_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
            self.master.recv_match(type="MISSION_ACK", blocking=True, timeout=2)

            total_count = len(waypoints) + 1  # +1: seq 0 = home rezerve slotu
            self.master.mav.mission_count_send(
                self.master.target_system,
                self.master.target_component,
                total_count,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )

            max_retries = total_count * 3 + 10
            attempts = 0

            while attempts < max_retries:
                attempts += 1

                msg = self.master.recv_match(
                    type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
                    blocking=True,
                    timeout=5,
                )
                if msg is None:
                    return False, "Zaman asimi: drondan cevap gelmedi"

                msg_type = msg.get_type()

                if msg_type == "MISSION_ACK":
                    if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                        return True, f"{len(waypoints)} waypoint basariyla yuklendi"
                    else:
                        return False, f"Drone gorevi reddetti (hata kodu: {msg.type})"

                seq = msg.seq
                if seq >= total_count:
                    continue

                if seq == 0:
                    # Home rezerve slotu: FC gercek home konumunu zaten biliyor
                    # (HOME_POSITION), burada gonderilen koordinat sadece
                    # protokol geregi bir yer tutucudur ve FC tarafindan
                    # navigasyon icin kullanilmaz.
                    self.master.mav.mission_item_int_send(
                        self.master.target_system,
                        self.master.target_component,
                        0,
                        mavutil.mavlink.MAV_FRAME_GLOBAL,
                        mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                        0,
                        0,
                        0, 0, 0, 0,
                        0,
                        0,
                        0,
                    )
                    continue

                lat, lon, alt = waypoints[seq - 1]
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    seq,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0,
                    1,
                    0, 0, 0, 0,
                    int(lat * 1e7),
                    int(lon * 1e7),
                    alt,
                )

            return False, "Cok fazla deneme yapildi, gorev tamamlanamadi"

        except Exception as e:
            return False, f"Gorev yukleme hatasi: {e}"

    def download_mission(self):
        """
        Gorevi FC'den oku (readback):
          MISSION_REQUEST_LIST -> MISSION_COUNT -> her seq icin
          MISSION_REQUEST_INT -> MISSION_ITEM_INT, en sonda MISSION_ACK.
        Donus: (ok, mesaj, [(lat, lon, alt), ...])
        """
        try:
            while self.master.recv_match(blocking=False) is not None:
                pass

            self.master.mav.mission_request_list_send(
                self.master.target_system,
                self.master.target_component,
            )

            count_msg = self.master.recv_match(
                type="MISSION_COUNT", blocking=True, timeout=5
            )
            if count_msg is None:
                return False, "MISSION_COUNT gelmedi (zaman asimi)", []

            count = int(count_msg.count)
            if count <= 0:
                return True, "Dronda kayitli gorev yok", []

            raw_items = []
            for seq in range(count):
                self.master.mav.mission_request_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    seq,
                )
                item = self.master.recv_match(
                    type=["MISSION_ITEM_INT", "MISSION_ITEM"],
                    blocking=True,
                    timeout=5,
                )
                if item is None:
                    return False, f"Waypoint {seq} indirilemedi (zaman asimi)", []
                raw_items.append(item)

            try:
                self.master.mav.mission_ack_send(
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_MISSION_ACCEPTED,
                )
            except Exception:
                pass

            waypoints = []
            for item in raw_items:
                command = int(item.command)
                if command not in _NAV_COMMANDS:
                    continue
                if item.get_type() == "MISSION_ITEM_INT":
                    lat = item.x / 1e7
                    lon = item.y / 1e7
                else:
                    lat = float(item.x)
                    lon = float(item.y)
                alt = float(item.z)
                # Seq 0 cogu zaman home; lat/lon 0 olanlari atla
                if abs(lat) < 1e-8 and abs(lon) < 1e-8:
                    continue
                if int(item.seq) == 0 and command == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT:
                    continue
                waypoints.append((lat, lon, alt))

            return True, f"{len(waypoints)} waypoint drondan indirildi", waypoints

        except Exception as e:
            return False, f"Gorev indirme hatasi: {e}", []

    def clear_mission(self):
        """
        FC'nin gorev hafizasindaki TUM waypoint'leri siler (MISSION_CLEAR_ALL)
        ve MISSION_ACK ile onaylanmasini bekler. GCS'in yerel tablosunu SILMEZ;
        onu cagiran taraf (MissionPanel/MainWindow) ayrica temizlemelidir.
        """
        try:
            while self.master.recv_match(blocking=False) is not None:
                pass

            self.master.mav.mission_clear_all_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
            ack = self.master.recv_match(type="MISSION_ACK", blocking=True, timeout=3)
            if ack is None:
                return False, "Zaman asimi: MISSION_ACK gelmedi"
            if ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                return True, "Dronun gorev hafizasi temizlendi"
            return False, f"Gorev temizleme reddedildi (hata kodu: {ack.type})"
        except Exception as e:
            return False, f"Gorev temizleme hatasi: {e}"

    def upload_fence_polygon(self, points):
        """
        points: [(lat, lon), ...] en az 3 nokta. ArduPilot poligon fence
        yukleme protokolu, mission protokolunun MAV_MISSION_TYPE_FENCE
        tipiyle aynidir. Her vertex MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION
        komutuyla gonderilir; param1 toplam vertex sayisidir (her mesajda
        ayni deger tekrarlanir - FC bu sekilde poligonun tamamlandigini anlar).
        """
        if not points or len(points) < 3:
            return False, "En az 3 nokta gerekli"
        try:
            self.master.mav.mission_clear_all_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
            )
            self.master.recv_match(type="MISSION_ACK", blocking=True, timeout=2)

            count = len(points)
            self.master.mav.mission_count_send(
                self.master.target_system,
                self.master.target_component,
                count,
                mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
            )

            max_retries = count * 3 + 10
            attempts = 0
            while attempts < max_retries:
                attempts += 1
                msg = self.master.recv_match(
                    type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
                    blocking=True,
                    timeout=5,
                )
                if msg is None:
                    return False, "Zaman asimi: drondan cevap gelmedi"
                msg_type = msg.get_type()
                if msg_type == "MISSION_ACK":
                    if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                        return True, f"{count} noktali poligon fence yuklendi"
                    return False, f"Poligon reddedildi (hata kodu: {msg.type})"
                seq = msg.seq
                if seq >= count:
                    continue
                lat, lon = points[seq]
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    seq,
                    mavutil.mavlink.MAV_FRAME_GLOBAL,
                    mavutil.mavlink.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION,
                    0,
                    1,
                    float(count), 0, 0, 0,
                    int(lat * 1e7),
                    int(lon * 1e7),
                    0,
                    mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
                )
            return False, "Cok fazla deneme yapildi, poligon tamamlanamadi"
        except Exception as e:
            return False, f"Poligon yukleme hatasi: {e}"

    def download_fence_polygon(self):
        """FC'deki poligon fence'i okur. Donus: (ok, mesaj, [(lat, lon), ...])"""
        try:
            while self.master.recv_match(blocking=False) is not None:
                pass
            self.master.mav.mission_request_list_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
            )
            count_msg = self.master.recv_match(type="MISSION_COUNT", blocking=True, timeout=5)
            if count_msg is None:
                return False, "MISSION_COUNT gelmedi (zaman asimi)", []
            count = int(count_msg.count)
            if count <= 0:
                return True, "FC'de kayitli poligon fence yok", []
            points = []
            for seq in range(count):
                self.master.mav.mission_request_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    seq,
                    mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
                )
                item = self.master.recv_match(
                    type=["MISSION_ITEM_INT", "MISSION_ITEM"], blocking=True, timeout=5
                )
                if item is None:
                    return False, f"Nokta {seq} indirilemedi (zaman asimi)", []
                if int(item.command) != mavutil.mavlink.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION:
                    continue
                if item.get_type() == "MISSION_ITEM_INT":
                    lat = item.x / 1e7
                    lon = item.y / 1e7
                else:
                    lat = float(item.x)
                    lon = float(item.y)
                points.append((lat, lon))
            try:
                self.master.mav.mission_ack_send(
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_MISSION_ACCEPTED,
                    mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
                )
            except Exception:
                pass
            return True, f"{len(points)} noktali poligon fence indirildi", points
        except Exception as e:
            return False, f"Poligon indirme hatasi: {e}", []

    def clear_fence_polygon(self):
        """FC'nin poligon fence hafizasini tamamen siler (MISSION_CLEAR_ALL,
        MAV_MISSION_TYPE_FENCE ile)."""
        try:
            while self.master.recv_match(blocking=False) is not None:
                pass
            self.master.mav.mission_clear_all_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
            )
            ack = self.master.recv_match(type="MISSION_ACK", blocking=True, timeout=3)
            if ack is None:
                return False, "Zaman asimi: MISSION_ACK gelmedi"
            if ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                return True, "Poligon fence FC'den silindi"
            return False, f"Poligon silme reddedildi (hata kodu: {ack.type})"
        except Exception as e:
            return False, f"Poligon silme hatasi: {e}"            
    def _decode_sensor_health(self, msg):
        """
        SYS_STATUS.onboard_control_sensors_enabled / _health bit maskelerini
        safety_panel.py'nin bekledigi {sensor_adi: True/False/None} sozlugune
        cevirir. None = bu arac icin bu sensor hic raporlanmiyor (bit
        enabled'da kapali), True/False = sensor var ve saglikli/arizali.
        """
        enabled = msg.onboard_control_sensors_enabled
        health = msg.onboard_control_sensors_health
        sensors = {}
        for key, bit in _SENSOR_BITS.items():
            if enabled & bit:
                sensors[key] = bool(health & bit)
            else:
                sensors[key] = None
        return sensors
    def request_prearm_check(self):
        """
        Gercekten ARM etmeden, otopilotun PreArm kontrollerini yeniden
        calistirmasini ister (MAV_CMD_RUN_PREARM_CHECKS = 401). Bunu
        duzenli araliklarla cagirmazsak, PreArm STATUSTEXT mesaji sadece
        gercek bir ARM denemesinde BIR KEZ gelir; birkac saniye sonra
        GCS'te "cozulmus" sanilip listeden dusurulur - sorun hala
        duruyor olsa bile.
        """
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                401,  # MAV_CMD_RUN_PREARM_CHECKS
                0,
                0, 0, 0, 0, 0, 0, 0,
            )
        except Exception as e:
            print(f"[DroneTelemetry] PreArm kontrolu istenemedi: {e}")
    _FAILSAFE_PARAMS = ["RTL_ALT_M", "FS_BATT_ENABLE", "BATT_LOW_VOLT"]
    def request_fence_params(self):
        """Dairesel geofence icin FENCE_ENABLE, FENCE_RADIUS, FENCE_ALT_MAX
        parametrelerini FC'den ister (PARAM_REQUEST_READ). Yanitlar
        PARAM_VALUE mesaji olarak get_telemetry_data() uzerinden gelir."""

        for name in _FENCE_PARAMS:
            try:
                self.master.mav.param_request_read_send(
                    self.master.target_system,
                    self.master.target_component,
                    name.encode("utf-8"),
                    -1,
                )
            except Exception as e:
                print(f"[DroneTelemetry] {name} istenemedi: {e}")

    def request_failsafe_params(self):
        """RTL_ALT, FS_BATT_ENABLE, BATT_LOW_VOLT parametrelerini FC'den
        ister."""
        for name in _FAILSAFE_PARAMS:
            try:
                self.master.mav.param_request_read_send(
                    self.master.target_system,
                    self.master.target_component,
                    name.encode("utf-8"),
                    -1,
                )
            except Exception as e:
                print(f"[DroneTelemetry] {name} istenemedi: {e}")

    def request_single_param(self, name: str):
        """Herhangi bir tek parametreyi FC'den ister (genel amacli)."""
        try:
            self.master.mav.param_request_read_send(
                self.master.target_system,
                self.master.target_component,
                name.encode("utf-8"),
                -1,
            )
        except Exception as e:
            print(f"[DroneTelemetry] {name} istenemedi: {e}")
    def set_fence_params(self, enabled: bool, radius_m: float):
        """FENCE_ENABLE ve FENCE_RADIUS parametrelerini FC'ye yazar
        (PARAM_SET). Yazma onayi PARAM_VALUE mesaji olarak geri doner -
        bu yuzden yazdiktan hemen sonra request_fence_params() ile
        tekrar okuyup arayuzu guncel tutmak gerekir."""
        try:
            self.master.mav.param_set_send(
                self.master.target_system,
                self.master.target_component,
                b"FENCE_ENABLE",
                1.0 if enabled else 0.0,
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            self.master.mav.param_set_send(
                self.master.target_system,
                self.master.target_component,
                b"FENCE_RADIUS",
                float(radius_m),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
        except Exception as e:
            print(f"[DroneTelemetry] Fence parametreleri yazilamadi: {e}")

    def request_all_params(self):
        """Tum FC parametrelerini ister (PARAM_REQUEST_LIST). Yanitlar
        yuzlerce PARAM_VALUE mesaji olarak get_telemetry_data() uzerinden
        tek tek gelir; her mesaj kendi param_index/param_count degerini
        tasidigi icin indirme ilerlemesi izlenebilir."""
        try:
            self.master.mav.param_request_list_send(
                self.master.target_system,
                self.master.target_component,
            )
        except Exception as e:
            print(f"[DroneTelemetry] Parametre listesi istenemedi: {e}")

    def set_param(self, name: str, value: float, param_type: int):
        """Tek bir parametreyi FC'ye yazar (PARAM_SET). param_type,
        PARAM_VALUE mesajindan okunan orijinal turdur - ayni turu geri
        gondermek FC'nin degeri dogru yorumlamasini saglar."""
        try:
            self.master.mav.param_set_send(
                self.master.target_system,
                self.master.target_component,
                name.encode("utf-8"),
                float(value),
                int(param_type),
            )
        except Exception as e:
            print(f"[DroneTelemetry] {name} yazilamadi: {e}")
    def close(self):
        if self.master:
            try:
                self.master.close()
            except Exception:
                pass
            self.master = None
