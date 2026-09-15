"""
test_flight_summary.py
-----------------------
ADIM 1 dogrulamasi: ucus ozeti penceresi DISARM aninda KENDILIGINDEN
ACILMAMALI; bunun yerine "SON UCUS OZETI" butonu aktiflesmeli ve pilot
tikladiginda pencere dogru verilerle acilmali.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump


class SahteOzetPenceresi:
    """Gercek FlightSummaryDialog yerine gecer: exec_() ile bloklamaz,
    kendisine hangi verilerle kac kez acildigini kaydeder."""

    cagrilar = []

    def __init__(self, **kwargs):
        SahteOzetPenceresi.cagrilar.append(kwargs)

    def exec_(self):
        return 0


class FlightSummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected, "Sahte araca baglanilamadi"
        # Testler ayni pencereyi paylasir ve unittest onlari alfabetik
        # calistirir; "ucus oncesi" durumu bu yuzden burada, henuz hic ucus
        # yapilmamisken kaydedilir.
        cls.baslangic_buton_aktif = cls.win.btn_last_summary.isEnabled()
        cls.baslangic_ozet = cls.win._last_flight_summary
        # Testler gercek logs/ klasorune CSV birakmasin.
        cls._tmp = tempfile.TemporaryDirectory()
        cls.win.flight_logger.log_dir = cls._tmp.name

    @classmethod
    def tearDownClass(cls):
        cls.win.flight_logger.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()
        cls._tmp.cleanup()

    def setUp(self):
        SahteOzetPenceresi.cagrilar = []
        self._gercek = self.main_v7.FlightSummaryDialog
        self.main_v7.FlightSummaryDialog = SahteOzetPenceresi

    def tearDown(self):
        self.main_v7.FlightSummaryDialog = self._gercek

    def _ucus_yap(self, saniye=1.2):
        self.vehicle.armed = True
        self.assertTrue(
            pump(6.0, until=lambda: self.win.is_armed), "ARM arayuze yansimadi"
        )
        pump(saniye)
        self.vehicle.armed = False
        self.assertTrue(
            pump(6.0, until=lambda: not self.win.is_armed), "DISARM arayuze yansimadi"
        )
        pump(0.4)

    def test_ucus_oncesi_buton_pasif(self):
        """Hic ucus yapilmamisken (boot anindaki durum) buton pasif olmali."""
        self.assertFalse(self.baslangic_buton_aktif)
        self.assertIsNone(self.baslangic_ozet)

    def test_disarm_pencereyi_acmaz_butonu_aktiflestirir(self):
        """Asil regresyon: eskiden DISARM aninda pencere kendiliginden
        aciliyordu; RTL/LAND sirasindaki sahte DISARM gorunumleri bunu
        beklenmedik anlarda tetikliyordu."""
        self._ucus_yap()

        self.assertEqual(
            SahteOzetPenceresi.cagrilar, [],
            "Ozet penceresi DISARM aninda kendiliginden acildi",
        )
        self.assertTrue(
            self.win.btn_last_summary.isEnabled(), "Ozet butonu aktiflesmedi"
        )
        self.assertIn("SON UCUS OZETI", self.win.btn_last_summary.text())

    def test_butona_basinca_ozet_dogru_verilerle_acilir(self):
        self._ucus_yap()
        self.win.btn_last_summary.click()
        pump(0.2)

        self.assertEqual(len(SahteOzetPenceresi.cagrilar), 1, "Ozet penceresi acilmadi")
        ozet = SahteOzetPenceresi.cagrilar[0]
        self.assertGreater(ozet["duration_s"], 0.0)
        # Sahte arac sabit 25 m irtifa yayinliyor.
        self.assertAlmostEqual(ozet["max_alt"], self.vehicle.rel_alt_m, places=1)
        self.assertIsNotNone(ozet["start_iso"])
        self.assertIs(ozet["parent"], self.win)

    def test_saklanan_ozet_tekrar_tekrar_acilabilir(self):
        self._ucus_yap()
        self.win.btn_last_summary.click()
        self.win.btn_last_summary.click()
        pump(0.2)
        self.assertEqual(len(SahteOzetPenceresi.cagrilar), 2)

    def test_ucus_yokken_butona_basmak_guvenli(self):
        self.win._last_flight_summary = None
        self.win.on_last_summary_clicked()  # istisna firlatmamali
        self.assertEqual(SahteOzetPenceresi.cagrilar, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
