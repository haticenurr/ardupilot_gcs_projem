"""
test_rssi.py
-------------
ADIM 5 dogrulamasi: telemetri radyosu sinyal kalitesi gostergesi.

Onemli davranis: RADIO_STATUS gelmiyorsa (SITL bu mesaji uretmez)
gosterge "--" kalmali, uygulama hata vermemeli.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.drone_telemetry import RSSI_MAX
from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump


class RssiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected, "Sahte araca baglanilamadi"
        # RADIO_STATUS hic gonderilmemisken gostergenin durumu.
        cls.baslangic_degeri = cls.win.card_rssi.value_label.text()

    @classmethod
    def tearDownClass(cls):
        cls.win.worker.stop()
        cls.vehicle.stop()

    def test_veri_yokken_gosterge_bos_kalir(self):
        """SITL RADIO_STATUS uretmez; kart '--' kalmali, cokmemeli."""
        self.assertEqual(self.baslangic_degeri, "--")

    def test_yuzde_dogru_hesaplanir(self):
        # 255 -> %100 olcegi
        self.vehicle.send_radio_status(rssi=255, remrssi=255)
        pump(3.0, until=lambda: self.win.current_rssi == 100)
        self.assertEqual(self.win.current_rssi, 100)
        self.assertEqual(self.win.card_rssi.value_label.text(), "100")

    def test_zayif_olan_uc_gosterilir(self):
        """Baglantinin gercek kalitesini iki uctan DUSUK olani belirler."""
        beklenen = round(51 / RSSI_MAX * 100)  # ~%20
        self.vehicle.send_radio_status(rssi=255, remrssi=51)
        pump(3.0, until=lambda: self.win.current_rssi == beklenen)
        self.assertEqual(self.win.current_rssi, beklenen)

    def test_dusuk_sinyal_kirmizi_yuksek_sinyal_yesil(self):
        self.vehicle.send_radio_status(rssi=40, remrssi=40)  # ~%16
        pump(3.0, until=lambda: self.win.current_rssi is not None
             and self.win.current_rssi < 30)
        self.assertLess(self.win.current_rssi, 30)

        self.vehicle.send_radio_status(rssi=240, remrssi=240)  # ~%94
        pump(3.0, until=lambda: self.win.current_rssi is not None
             and self.win.current_rssi >= 60)
        self.assertGreaterEqual(self.win.current_rssi, 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
