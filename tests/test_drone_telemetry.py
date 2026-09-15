"""
test_drone_telemetry.py
------------------------
DroneTelemetry'yi gercek bir ucus kontrolcusu olmadan test eder: ayni
makinede UDP uzerinden konusan sahte bir arac (FakeVehicle) HEARTBEAT ve
telemetri yayinlar, GCS tarafi ona baglanir.

Calistirma:
    python -m unittest discover -s tests -v
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.drone_telemetry import DroneTelemetry, _RTL_ALT_PARAMS, _FAILSAFE_PARAMS
from fake_vehicle import FakeVehicle, free_udp_port


class DroneTelemetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        port = free_udp_port()
        cls.vehicle = FakeVehicle(port)
        cls.vehicle.start()
        cls.drone = DroneTelemetry(f"udpin:127.0.0.1:{port}")

    @classmethod
    def tearDownClass(cls):
        cls.drone.close()
        cls.vehicle.stop()

    def _read_until(self, msg_type, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self.drone.get_telemetry_data()
            if data and data.get("type") == msg_type:
                return data
            time.sleep(0.01)
        return None

    def test_arac_heartbeatine_kilitlenir(self):
        self.assertEqual(self.drone.master.target_system, 1)

    def test_heartbeat_cozumlenir(self):
        data = self._read_until("HEARTBEAT")
        self.assertIsNotNone(data, "HEARTBEAT cozumlenemedi")
        self.assertFalse(data["armed"])
        self.assertEqual(data["mode"], "GUIDED")

    def test_pozisyon_cozumlenir(self):
        data = self._read_until("GLOBAL_POSITION_INT")
        self.assertIsNotNone(data, "GLOBAL_POSITION_INT cozumlenemedi")
        self.assertAlmostEqual(data["lat"], 39.925533, places=5)
        self.assertAlmostEqual(data["alt"], 25.0, places=3)

    def test_failsafe_parametreleri_istenebilir(self):
        """Regresyon: _FAILSAFE_PARAMS sinif niteligi oldugu surece bu cagri
        NameError firlatiyordu, bu yuzden RTL/pil failsafe degerleri arayuze
        hic ulasmiyordu."""
        onceki = len(self.vehicle.messages_of("PARAM_REQUEST_READ"))
        self.drone.request_failsafe_params()  # istisna firlatmamali
        istenen = self.vehicle.wait_for(
            "PARAM_REQUEST_READ", onceki + len(_FAILSAFE_PARAMS)
        )
        adlar = {
            m.param_id.rstrip("\x00") if isinstance(m.param_id, str)
            else m.param_id.decode().rstrip("\x00")
            for m in istenen
        }
        for beklenen in _FAILSAFE_PARAMS:
            self.assertIn(beklenen, adlar)

    def test_rtl_irtifasi_iki_parametre_adina_da_dogru_birimde_yazilir(self):
        """RTL_ALT_M metre, eski RTL_ALT santimetre bekler."""
        onceki = len(self.vehicle.messages_of("PARAM_SET"))
        self.drone.set_rtl_altitude(45.0)
        yazilanlar = self.vehicle.wait_for("PARAM_SET", onceki + 2)
        degerler = {}
        for m in yazilanlar:
            pid = m.param_id
            if isinstance(pid, bytes):
                pid = pid.decode()
            degerler[pid.rstrip("\x00")] = m.param_value
        self.assertAlmostEqual(degerler.get("RTL_ALT_M"), 45.0, places=3)
        self.assertAlmostEqual(degerler.get("RTL_ALT"), 4500.0, places=1)

    def test_rtl_parametre_tablosu_tutarli(self):
        self.assertEqual(dict(_RTL_ALT_PARAMS)["RTL_ALT_M"], 1.0)
        self.assertEqual(dict(_RTL_ALT_PARAMS)["RTL_ALT"], 100.0)

    def test_bekleme_sirasinda_telemetri_yutulmaz(self):
        """Regresyon: mission/fence protokolu beklenirken gelen telemetri
        eskiden dusuruluyordu; arayuz saniyelerce donuyor ve heartbeat zaman
        asimi sahte 'baglanti kesildi' alarmi uretiyordu."""
        toplanan = []
        self.drone.telemetry_sink = toplanan.append
        try:
            # Sahte arac hic MISSION_ACK gondermiyor: bekleme zaman asimina
            # ugrayacak, ama bu sirada telemetri sink'e akmali.
            sonuc = self.drone._recv_match_pumped("MISSION_ACK", 1.5)
        finally:
            self.drone.telemetry_sink = None
        self.assertIsNone(sonuc, "Beklenmeyen MISSION_ACK")
        self.assertTrue(toplanan, "Bekleme sirasinda hic telemetri iletilmedi")
        turler = {d["type"] for d in toplanan}
        self.assertIn("HEARTBEAT", turler)

    def test_gorev_yuklenirken_telemetri_akmaya_devam_eder(self):
        """Regresyon: upload_mission bloklayici recv_match kullandigi surece
        yukleme boyunca (saniyeler) hic telemetri yayinlanmiyordu; heartbeat
        zaman asimi dolunca GCS sahte 'baglanti kesildi' alarmi veriyordu."""
        self.vehicle.mission_protocol = True
        self.vehicle.mission_delay = 0.12
        toplanan = []
        self.drone.telemetry_sink = toplanan.append
        try:
            ok, mesaj = self.drone.upload_mission(
                [(39.1, 32.1, 30.0), (39.2, 32.2, 40.0)]
            )
        finally:
            self.drone.telemetry_sink = None
            self.vehicle.mission_protocol = False
            self.vehicle.mission_delay = 0.0

        self.assertTrue(ok, f"Gorev yuklenemedi: {mesaj}")
        turler = {d["type"] for d in toplanan}
        self.assertIn(
            "HEARTBEAT", turler, "Yukleme sirasinda telemetri akmadi"
        )

    def test_ilk_waypoint_seq_1e_yazilir(self):
        """ArduPilot'ta seq=0 home slotudur; gercek waypointler seq=1'den
        baslamazsa arac ilk noktaya hic ugramaz."""
        self.vehicle.mission_protocol = True
        try:
            ok, mesaj = self.drone.upload_mission([(39.1, 32.1, 30.0)])
        finally:
            self.vehicle.mission_protocol = False
        self.assertTrue(ok, mesaj)
        items = {int(m.seq): m for m in self.vehicle.messages_of("MISSION_ITEM_INT")}
        self.assertIn(0, items, "Home rezerve slotu gonderilmedi")
        self.assertIn(1, items, "Ilk gercek waypoint seq=1'e yazilmadi")
        self.assertAlmostEqual(items[1].x / 1e7, 39.1, places=5)
        self.assertAlmostEqual(items[1].y / 1e7, 32.1, places=5)
        self.assertAlmostEqual(items[1].z, 30.0, places=3)

    def test_drain_pending_telemetriyi_iletir(self):
        """Kuyruk bosaltma protokol artiklarini atmali, telemetriyi degil."""
        time.sleep(0.4)  # tamponda mesaj birikmesi icin
        toplanan = []
        self.drone.telemetry_sink = toplanan.append
        try:
            self.drone._drain_pending()
        finally:
            self.drone.telemetry_sink = None
        self.assertTrue(toplanan, "_drain_pending telemetriyi yuttu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
