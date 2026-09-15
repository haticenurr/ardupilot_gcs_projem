"""
test_arm_hata_bildirimi.py
---------------------------
ARM reddedildiginde kullanici SEBEBINI gormeli.

Regresyon: gorev sihirbazi send_arm_disarm()'in donusunu yok sayiyor,
12 saniye bekleyip yalnizca "Hata: ARM gerceklesmedi" yaziyordu. FC'nin
bildirdigi asil sebep (orn. "PreArm: 3D Accel calibration needed")
hicbir yerde gosterilmiyordu. Ayrica red mesaji ciplak sayisal kod
iceriyordu ("kod: 4").
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymavlink import mavutil

from core.drone_telemetry import DroneTelemetry
from fake_vehicle import FakeVehicle, free_udp_port


class ArmRedMesajiTest(unittest.TestCase):
    """DroneTelemetry katmani: red mesaji okunabilir olmali."""

    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.drone = DroneTelemetry(f"udpin:127.0.0.1:{cls.vehicle.port}")

    @classmethod
    def tearDownClass(cls):
        cls.drone.close()
        cls.vehicle.stop()

    def tearDown(self):
        self.vehicle.arm_ack_result = None
        self.vehicle.prearm_text = None

    def test_red_mesaji_okunabilir_sonuc_adi_icerir(self):
        self.vehicle.arm_ack_result = mavutil.mavlink.MAV_RESULT_FAILED
        ok, mesaj = self.drone.send_arm_disarm(True)
        self.assertFalse(ok)
        self.assertIn("MAV_RESULT_FAILED", mesaj)
        self.assertNotIn("kod:", mesaj, "Ciplak sayisal kod hala gosteriliyor")

    def test_kabul_edilen_arm_basarili_doner(self):
        self.vehicle.arm_ack_result = mavutil.mavlink.MAV_RESULT_ACCEPTED
        ok, mesaj = self.drone.send_arm_disarm(True)
        self.assertTrue(ok)
        self.assertIn("ARM basarili", mesaj)

    def test_yanit_gelmezse_zaman_asimi_bildirilir(self):
        self.vehicle.arm_ack_result = None
        ok, mesaj = self.drone.send_arm_disarm(True)
        self.assertFalse(ok)
        self.assertIn("Zaman asimi", mesaj)


class PrearmSebebiTest(unittest.TestCase):
    """Worker katmani: PreArm uyarisi hata mesajina eklenmeli."""

    def _worker(self):
        import main_v7

        w = main_v7.TelemetryWorker.__new__(main_v7.TelemetryWorker)
        w._last_prearm_text = ""
        w._last_prearm_ts = 0.0
        return w

    def test_prearm_uyarisi_mesaja_eklenir(self):
        w = self._worker()
        w._process_telemetry_data(
            {"type": "STATUSTEXT", "text": "PreArm: 3D Accel calibration needed"}
        )
        mesaj = w._arm_hata_sebebi("ARM gerceklesmedi")
        self.assertIn("ARM gerceklesmedi", mesaj)
        self.assertIn("3D Accel calibration needed", mesaj)

    def test_ilgisiz_statustext_sebep_sayilmaz(self):
        w = self._worker()
        w._process_telemetry_data(
            {"type": "STATUSTEXT", "text": "EKF3 IMU0 is using GPS"}
        )
        self.assertEqual(w._arm_hata_sebebi("ARM gerceklesmedi"), "ARM gerceklesmedi")

    def test_eski_prearm_uyarisi_kullanilmaz(self):
        """15 saniyeden eski bir uyari, bu ARM denemesine ait degildir."""
        w = self._worker()
        w._process_telemetry_data(
            {"type": "STATUSTEXT", "text": "PreArm: Compass not calibrated"}
        )
        w._last_prearm_ts = time.time() - 60
        self.assertEqual(w._arm_hata_sebebi("ARM gerceklesmedi"), "ARM gerceklesmedi")

    def test_arm_onekli_mesaj_da_yakalanir(self):
        w = self._worker()
        w._process_telemetry_data(
            {"type": "STATUSTEXT", "text": "Arm: Motors Emergency Stopped"}
        )
        self.assertIn("Emergency Stopped", w._arm_hata_sebebi("ARM gerceklesmedi"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
