"""
test_battery.py
----------------
ADIM 9 dogrulamasi: pil hesaplari ve eve donus menzili.

Tasarim karari: eksik veriyle TAHMIN URETILMEZ. Yanlis bir menzil
tahmini pilota sahte guven verir; bilinmeyen girdide hesap
"hesaplanabildi=False" doner ve arayuz '--' gosterir.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.battery import (
    eve_donus_tahmini,
    hucre_sayisi_tahmini,
    kalan_mah,
    kalan_ucus_suresi_s,
)
from core.drone_telemetry import DroneTelemetry
from fake_vehicle import FakeVehicle, free_udp_port


class KalanEnerjiTest(unittest.TestCase):
    def test_kalan_mah(self):
        self.assertEqual(kalan_mah(5000, 3200), 1800)

    def test_tuketilen_kapasiteyi_asarsa_sifirlanir(self):
        self.assertEqual(kalan_mah(5000, 6000), 0.0)

    def test_bilinmeyen_girdi_none_doner(self):
        self.assertIsNone(kalan_mah(None, 100))
        self.assertIsNone(kalan_mah(0, 100))
        self.assertIsNone(kalan_mah(5000, None))
        self.assertIsNone(kalan_mah(5000, -1))

    def test_kalan_ucus_suresi(self):
        """1800 mAh / 18 A = 0.1 saat = 6 dakika."""
        self.assertAlmostEqual(kalan_ucus_suresi_s(1800, 18.0), 360.0, places=3)

    def test_akim_bilinmiyorsa_sure_hesaplanmaz(self):
        self.assertIsNone(kalan_ucus_suresi_s(1800, None))
        self.assertIsNone(kalan_ucus_suresi_s(1800, -1))
        self.assertIsNone(kalan_ucus_suresi_s(1800, 0))
        self.assertIsNone(kalan_ucus_suresi_s(None, 18.0))


class EveDonusTest(unittest.TestCase):
    def test_yakin_mesafede_yeterli(self):
        t = eve_donus_tahmini(
            mesafe_m=1200, hiz_ms=8, akim_a=18.0,
            kalan_mah_degeri=1800, kapasite_mah=5000,
        )
        self.assertTrue(t["hesaplanabildi"])
        self.assertAlmostEqual(t["sure_s"], 150.0, places=3)
        self.assertAlmostEqual(t["gereken_mah"], 750.0, places=1)
        self.assertAlmostEqual(t["yedek_mah"], 1000.0, places=1)
        self.assertTrue(t["yeterli"])

    def test_uzak_mesafede_yetersiz(self):
        t = eve_donus_tahmini(
            mesafe_m=6000, hiz_ms=8, akim_a=18.0,
            kalan_mah_degeri=1800, kapasite_mah=5000,
        )
        self.assertFalse(t["yeterli"])
        self.assertGreater(t["gereken_mah"], t["kalan_mah"] + t["yedek_mah"])

    def test_yedek_pay_hesaba_katilir(self):
        """Enerji tam yetse bile yedek payi dusulunce yetmeyebilir."""
        tam = eve_donus_tahmini(
            mesafe_m=3000, hiz_ms=8, akim_a=18.0,
            kalan_mah_degeri=1900, kapasite_mah=5000, yedek_orani=0.0,
        )
        yedekli = eve_donus_tahmini(
            mesafe_m=3000, hiz_ms=8, akim_a=18.0,
            kalan_mah_degeri=1900, kapasite_mah=5000, yedek_orani=0.20,
        )
        self.assertTrue(tam["yeterli"])
        self.assertFalse(yedekli["yeterli"])

    def test_kapasite_bilinmiyorsa_yedek_kalandan_hesaplanir(self):
        t = eve_donus_tahmini(
            mesafe_m=500, hiz_ms=8, akim_a=18.0, kalan_mah_degeri=2000
        )
        self.assertTrue(t["hesaplanabildi"])
        self.assertAlmostEqual(t["yedek_mah"], 400.0, places=1)

    def test_eksik_veriyle_tahmin_uretilmez(self):
        for kwargs in [
            dict(mesafe_m=None, hiz_ms=8, akim_a=18, kalan_mah_degeri=1800),
            dict(mesafe_m=1000, hiz_ms=0, akim_a=18, kalan_mah_degeri=1800),
            dict(mesafe_m=1000, hiz_ms=8, akim_a=None, kalan_mah_degeri=1800),
            dict(mesafe_m=1000, hiz_ms=8, akim_a=-1, kalan_mah_degeri=1800),
            dict(mesafe_m=1000, hiz_ms=8, akim_a=18, kalan_mah_degeri=None),
        ]:
            t = eve_donus_tahmini(**kwargs)
            self.assertFalse(t["hesaplanabildi"], kwargs)
            self.assertIsNone(t["yeterli"])

    def test_daha_hizli_donus_daha_az_enerji(self):
        yavas = eve_donus_tahmini(2000, 5, 18.0, 3000, kapasite_mah=5000)
        hizli = eve_donus_tahmini(2000, 10, 18.0, 3000, kapasite_mah=5000)
        self.assertLess(hizli["gereken_mah"], yavas["gereken_mah"])


class HucreTahminiTest(unittest.TestCase):
    def test_bilinen_paketler(self):
        self.assertEqual(hucre_sayisi_tahmini(22.2), 6)
        self.assertEqual(hucre_sayisi_tahmini(14.8), 4)
        self.assertEqual(hucre_sayisi_tahmini(11.1), 3)

    def test_gecersiz_gerilim(self):
        self.assertIsNone(hucre_sayisi_tahmini(0))
        self.assertIsNone(hucre_sayisi_tahmini(None))


class BatteryStatusCozumlemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.drone = DroneTelemetry(f"udpin:127.0.0.1:{cls.vehicle.port}")

    @classmethod
    def tearDownClass(cls):
        cls.drone.close()
        cls.vehicle.stop()

    def _oku(self, timeout=5.0):
        import time

        bitis = time.time() + timeout
        while time.time() < bitis:
            v = self.drone.get_telemetry_data()
            if v and v.get("type") == "BATTERY_STATUS":
                return v
            if v is None:
                time.sleep(0.005)
        return None

    def test_akim_ve_tuketim_cozumlenir(self):
        self.vehicle.send_battery_status(
            voltaj=22.2, akim_a=18.0, tuketilen_mah=1200, kalan_yuzde=64, hucre=6
        )
        v = self._oku()
        self.assertIsNotNone(v, "BATTERY_STATUS cozumlenemedi")
        self.assertAlmostEqual(v["akim_a"], 18.0, places=2)
        self.assertAlmostEqual(v["tuketilen_mah"], 1200.0, places=1)
        self.assertEqual(v["kalan_yuzde"], 64)
        self.assertEqual(v["hucre_sayisi"], 6)
        self.assertAlmostEqual(v["voltaj"], 22.2, delta=0.05)

    def test_bilinmeyen_akim_none_olur(self):
        """FC akimi olcemiyorsa -1 bildirir; bu 'bilinmiyor' demektir,
        sifir amper degil."""
        self.vehicle.send_battery_status(akim_a=None, tuketilen_mah=None)
        v = self._oku()
        self.assertIsNotNone(v)
        self.assertIsNone(v["akim_a"])
        self.assertIsNone(v["tuketilen_mah"])

    def test_kullanilmayan_hucreler_voltaja_katilmaz(self):
        """voltages dizisindeki 65535 dolgu degerleri toplanmamali."""
        self.vehicle.send_battery_status(voltaj=14.8, hucre=4)
        v = self._oku()
        self.assertIsNotNone(v)
        self.assertEqual(v["hucre_sayisi"], 4)
        self.assertAlmostEqual(v["voltaj"], 14.8, delta=0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
