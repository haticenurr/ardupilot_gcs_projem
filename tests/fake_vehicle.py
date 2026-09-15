"""
fake_vehicle.py
----------------
Testlerde kullanilan sahte otopilot. Ayni makinede UDP uzerinden MAVLink
konusur; gercek bir ucus kontrolcusu veya SITL gerektirmez.

- HEARTBEAT ve GLOBAL_POSITION_INT yayinlar (`armed` alani ile ARM/DISARM
  taklidi yapilir)
- Gelen tum mesajlari kaydeder (`messages_of`, `wait_for`)
- `mission_protocol` acildiginda gorev yukleme protokolune yanit verir
"""

import socket
import threading
import time

from pymavlink import mavutil


def free_udp_port():
    """Test icin bos bir UDP portu bulur (sabit 14550 ile cakismayi onler)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeVehicle:
    """HEARTBEAT yayinlayan, gelen mesajlari kaydeden sahte otopilot."""

    def __init__(self, port):
        self.port = port
        self.conn = mavutil.mavlink_connection(
            f"udpout:127.0.0.1:{port}", source_system=1, source_component=1
        )
        self.received = []
        self._lock = threading.Lock()
        self._running = True

        # ARM durumu: testler bunu degistirerek ucus baslatip bitirir.
        self.armed = False
        # Bildirilen ucus modu (ArduCopter custom_mode). 4 = GUIDED.
        self.custom_mode = 4
        # Kalkis noktasina gore irtifa (metre).
        self.rel_alt_m = 25.0

        # Gorev protokolu taklidi: acildiginda MISSION_COUNT'a
        # MISSION_REQUEST_INT'lerle, son item'dan sonra MISSION_ACK ile
        # yanit verir. mission_delay her yanitin oncesine gecikme koyar;
        # boylece yukleme birkac heartbeat suresi kadar uzar ve bu sirada
        # telemetrinin akmaya devam ettigi olculebilir.
        self.mission_protocol = False
        self.mission_delay = 0.0
        self._mission_count = 0

        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._running = False
        self._thread.join(timeout=3)
        self.conn.close()

    def _loop(self):
        while self._running:
            self.send_heartbeat()
            self.send_position()
            deadline = time.time() + 0.1
            while time.time() < deadline:
                msg = self.conn.recv_match(blocking=False)
                if msg is None:
                    time.sleep(0.005)
                    continue
                with self._lock:
                    self.received.append(msg)
                if self.mission_protocol:
                    self._handle_mission(msg)

    def _handle_mission(self, msg):
        t = msg.get_type()
        if t not in ("MISSION_CLEAR_ALL", "MISSION_COUNT", "MISSION_ITEM_INT"):
            return
        if self.mission_delay:
            time.sleep(self.mission_delay)
        if t == "MISSION_CLEAR_ALL":
            self.conn.mav.mission_ack_send(255, 0, mavutil.mavlink.MAV_MISSION_ACCEPTED)
        elif t == "MISSION_COUNT":
            self._mission_count = int(msg.count)
            self.conn.mav.mission_request_int_send(255, 0, 0)
        elif t == "MISSION_ITEM_INT":
            nxt = int(msg.seq) + 1
            if nxt < self._mission_count:
                self.conn.mav.mission_request_int_send(255, 0, nxt)
            else:
                self.conn.mav.mission_ack_send(
                    255, 0, mavutil.mavlink.MAV_MISSION_ACCEPTED
                )

    def send_heartbeat(self):
        base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if self.armed:
            base_mode |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        self.conn.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_QUADROTOR,
            mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
            base_mode,
            self.custom_mode,
            mavutil.mavlink.MAV_STATE_ACTIVE,
        )

    def send_position(self):
        self.conn.mav.global_position_int_send(
            int(time.time() * 1000) & 0xFFFFFFFF,
            int(39.925533 * 1e7), int(32.866287 * 1e7),
            100000, int(self.rel_alt_m * 1000), 0, 0, 0, 0,
        )

    def send_sys_status(self, battery_remaining, voltage_v=11.1):
        """Pil yuzdesi iceren SYS_STATUS. Sensor bitleri saglikli verilir."""
        bits = (
            mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_GYRO
            | mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_ACCEL
            | mavutil.mavlink.MAV_SYS_STATUS_SENSOR_GPS
            | mavutil.mavlink.MAV_SYS_STATUS_SENSOR_BATTERY
        )
        self.conn.mav.sys_status_send(
            bits, bits, bits, 250,
            int(voltage_v * 1000), -1, int(battery_remaining),
            0, 0, 0, 0, 0, 0,
        )

    def send_radio_status(self, rssi=200, remrssi=180, noise=20, remnoise=25, rxerrors=0):
        """Telemetri radyosunun sinyal raporu. SITL bunu uretmez; gercek
        SiK radyolarda saniyede bir gelir."""
        self.conn.mav.radio_status_send(
            rssi, remrssi, 100, noise, remnoise, rxerrors, 0
        )

    # --- kalibrasyon taklidi ---

    def send_mag_cal_progress(self, completion_pct, cal_status=2, compass_id=0):
        """FC'nin pusula kalibrasyonu sirasinda yayinladigi ilerleme mesaji."""
        self.conn.mav.mag_cal_progress_send(
            compass_id, 1, cal_status, 1, int(completion_pct),
            bytes(10), 0.0, 0.0, 0.0,
        )

    def send_mag_cal_report(self, cal_status=4, fitness=2.5, compass_id=0, autosaved=0):
        """Kalibrasyon sonucu. cal_status=4 -> basarili."""
        self.conn.mav.mag_cal_report_send(
            compass_id, 1, cal_status, autosaved, float(fitness),
            0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0,
        )

    def send_statustext(self, text, severity=6):
        self.conn.mav.statustext_send(
            severity, text.encode("utf-8")[:50].ljust(50, b"\x00")
        )

    def commands_of(self, command_id):
        """Gonderilen COMMAND_LONG mesajlarindan yalnizca istenen komutu suzer
        (GET_HOME_POSITION / RUN_PREARM_CHECKS gibi arka plan komutlari elenir)."""
        return [
            m for m in self.messages_of("COMMAND_LONG")
            if int(m.command) == int(command_id)
        ]

    def wait_for_command(self, command_id, count=1, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.commands_of(command_id)
            if len(found) >= count:
                return found
            time.sleep(0.05)
        return self.commands_of(command_id)

    def messages_of(self, msg_type):
        with self._lock:
            return [m for m in self.received if m.get_type() == msg_type]

    def wait_for(self, msg_type, count=1, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.messages_of(msg_type)
            if len(found) >= count:
                return found
            time.sleep(0.05)
        return self.messages_of(msg_type)


if __name__ == "__main__":
    # Elle deneme icin: SITL kurmadan arayuzu canli veriyle gormek istersen
    #     python tests/fake_vehicle.py
    # komutunu ayri bir terminalde calistir, sonra GCS'i ac. Enter'a basarak
    # ARM/DISARM yapabilir, ucus ozeti butonunu test edebilirsin.
    import argparse

    ayristirici = argparse.ArgumentParser(description="Sahte ArduCopter (test araci)")
    ayristirici.add_argument("--port", type=int, default=14550)
    secenek = ayristirici.parse_args()

    arac = FakeVehicle(secenek.port)
    arac.start()
    print(f"Sahte arac yayinda: udp 127.0.0.1:{secenek.port}")
    print("Komutlar:  [Enter] ARM/DISARM  ·  r = RADIO_STATUS  ·  f = fence ihlali")
    print("           b = dusuk pil       ·  q = cikis")
    try:
        while True:
            komut = input("> ").strip().lower()
            if komut == "q":
                break
            elif komut == "r":
                arac.send_radio_status(rssi=200, remrssi=170)
                print("  RADIO_STATUS gonderildi")
            elif komut == "f":
                arac.send_statustext("Fence breach: circle", severity=4)
                print("  Geofence ihlali gonderildi")
            elif komut == "b":
                arac.send_sys_status(battery_remaining=15)
                print("  Dusuk pil (%15) gonderildi")
            else:
                arac.armed = not arac.armed
                print(f"  ARM durumu: {'ARMED' if arac.armed else 'DISARMED'}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        arac.stop()
        print("Sahte arac durduruldu.")
