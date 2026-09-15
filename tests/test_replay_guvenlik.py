"""
test_replay_guvenlik.py
------------------------
Kayit oynatma (replay) ile canli telemetrinin cakismasi.

BULUNAN HATA
------------
`update_telemetry_ui`, oynatma sirasinda fonksiyonun EN BASINDA kosulsuz
return ediyordu. ARM tespiti de ayni fonksiyonun icinde oldugu icin,
oynatma bir kez baslayinca arac ARM olsa bile GCS bunu HIC fark etmiyordu:
pilot, havadaki bir aracin yaninda kayitli ucusun irtifa, konum ve pil
degerlerini CANLI saniyordu.

Simdi HEARTBEAT her zaman islenir; ARM tespit edilince oynatma durur ve
canli telemetriye donulur.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump

CSV_BASLIK = "timestamp,lat,lon,alt,groundspeed,heading,battery,mode,armed\n"
CSV_SATIR = "2026-09-15 10:00:0{i},39.92{i},32.86{i},{a}.0,3.0,90,{b},GUIDED,True\n"


class ReplayGuvenlikTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected

        # Oynatilacak sahte kayit
        cls._tmp = tempfile.TemporaryDirectory()
        cls.kayit = os.path.join(cls._tmp.name, "flight_test.csv")
        with open(cls.kayit, "w", encoding="utf-8") as f:
            f.write(CSV_BASLIK)
            for i in range(9):
                f.write(CSV_SATIR.format(i=i, a=100 + i, b=90 - i))
        cls.win.replay_panel.log_dir = cls._tmp.name
        cls.win.replay_panel.refresh_file_list()

    @classmethod
    def tearDownClass(cls):
        cls.win.voice.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()
        cls._tmp.cleanup()

    def setUp(self):
        self.vehicle.armed = False
        pump(6.0, until=lambda: not self.win.is_armed)
        self.win.replay_panel.reset_playback()
        self.win.is_replaying = False
        self.win.replay_panel.set_armed(False)
        pump(0.3)

    def _kaydi_yukle(self):
        self.win.replay_panel.load_selected_file()
        pump(0.3)
        self.assertTrue(self.win.replay_panel.rows, "Kayit yuklenemedi")

    def test_disarm_haldeyken_oynatma_calisir(self):
        self._kaydi_yukle()
        self.win.replay_panel.toggle_play()
        pump(0.5)
        self.assertTrue(self.win.is_replaying, "Oynatma baslamadi")
        self.win.replay_panel.reset_playback()

    def test_arm_haldeyken_oynatma_baslatilamaz(self):
        self._kaydi_yukle()
        self.vehicle.armed = True
        self.assertTrue(pump(8.0, until=lambda: self.win.is_armed))
        pump(0.3)

        self.win.replay_panel.toggle_play()
        pump(0.5)
        self.assertFalse(
            self.win.is_replaying, "ARM durumda kayit oynatma baslatildi"
        )
        self.assertFalse(self.win.replay_panel.play_button.isEnabled())

    def test_oynatma_sirasinda_arm_olunca_canliya_donulur(self):
        """ASIL REGRESYON: eskiden oynatma baslayinca ARM hic fark
        edilmiyordu."""
        self._kaydi_yukle()
        self.win.replay_panel.toggle_play()
        pump(0.5)
        self.assertTrue(self.win.is_replaying)

        self.vehicle.armed = True
        self.assertTrue(
            pump(10.0, until=lambda: self.win.is_armed),
            "Oynatma sirasinda ARM tespit edilmedi",
        )
        self.assertFalse(
            self.win.is_replaying, "ARM sonrasi oynatma modundan cikilmadi"
        )

    def test_arm_sonrasi_canli_telemetri_yeniden_akar(self):
        self._kaydi_yukle()
        self.win.replay_panel.toggle_play()
        pump(0.5)
        self.win.current_alt = None

        self.vehicle.armed = True
        self.assertTrue(pump(10.0, until=lambda: self.win.is_armed))
        # Canli irtifa (sahte arac 25 m yayinliyor) yeniden gelmeli
        self.assertTrue(
            pump(6.0, until=lambda: self.win.current_alt is not None),
            "ARM sonrasi canli telemetri gelmedi",
        )
        self.assertAlmostEqual(
            self.win.current_alt, self.vehicle.rel_alt_m, places=1
        )

    def test_oynatma_sirasinda_canli_veri_arayuzu_ezmez(self):
        """Dogru davranis korunmali: DISARM haldeyken oynatma varken canli
        konum kartlari guncellenmemeli."""
        self._kaydi_yukle()
        self.win.replay_panel.toggle_play()
        pump(0.3)
        self.win.current_lat = None
        pump(1.5)
        self.assertIsNone(
            self.win.current_lat,
            "Oynatma sirasinda canli telemetri arayuzu ezdi",
        )
        self.win.replay_panel.reset_playback()


if __name__ == "__main__":
    unittest.main(verbosity=2)
