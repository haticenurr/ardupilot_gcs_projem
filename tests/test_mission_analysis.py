"""
test_mission_analysis.py
-------------------------
ADIM 8 dogrulamasi: gorev onizleme ve guvenlik analizi.

Bir waypoint'i yanlislikla geofence disina koymak, normalde ancak ucus
sirasinda failsafe tetiklendiginde anlasilir. Bu analiz onu yuklemeden
once yakalamali.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mission_analysis import (
    HATA,
    UYARI,
    analyze_mission,
    hata_sayisi,
    mesafe_metni,
    ozet_metni,
    sure_metni,
)

HOME = (39.9200, 32.8600)
# Home'dan kuzeye ~1111 m, ~2222 m
YAKIN = (39.9250, 32.8600, 30.0)   # ~556 m
ORTA = (39.9300, 32.8600, 40.0)    # ~1111 m
UZAK = (39.9400, 32.8600, 50.0)    # ~2222 m


def metinler(analiz, seviye=None):
    return [
        u["metin"] for u in analiz["uyarilar"]
        if seviye is None or u["seviye"] == seviye
    ]


class OlcumTest(unittest.TestCase):
    def test_bos_gorev_hata_verir(self):
        a = analyze_mission([])
        self.assertEqual(a["waypoint_sayisi"], 0)
        self.assertEqual(hata_sayisi(a), 1)

    def test_toplam_mesafe_evden_baslar(self):
        """Ilk bacak home -> waypoint 1 olmali; kalkis mesafesi sayilmazsa
        sure tahmini olduğundan kisa cikar."""
        ev_ile = analyze_mission([ORTA], home=HOME)
        evsiz = analyze_mission([ORTA])
        self.assertAlmostEqual(ev_ile["toplam_mesafe_m"], 1111.9, delta=10)
        self.assertEqual(evsiz["toplam_mesafe_m"], 0.0)

    def test_bacak_mesafeleri_listelenir(self):
        a = analyze_mission([YAKIN, ORTA, UZAK], home=HOME)
        # home->1, 1->2, 2->3
        self.assertEqual(len(a["bacak_mesafeleri_m"]), 3)
        self.assertAlmostEqual(sum(a["bacak_mesafeleri_m"]), a["toplam_mesafe_m"])

    def test_sure_hiza_gore_hesaplanir(self):
        yavas = analyze_mission([ORTA], home=HOME, speed_ms=5.0)
        hizli = analyze_mission([ORTA], home=HOME, speed_ms=10.0)
        self.assertAlmostEqual(yavas["tahmini_sure_s"], 2 * hizli["tahmini_sure_s"])

    def test_gecersiz_hiz_varsayilana_duser(self):
        a = analyze_mission([ORTA], home=HOME, speed_ms=0)
        self.assertGreater(a["tahmini_sure_s"], 0)

    def test_eve_en_uzak_ve_donus_mesafesi(self):
        a = analyze_mission([UZAK, ORTA], home=HOME)
        self.assertAlmostEqual(a["eve_en_uzak_m"], 2223.9, delta=15)
        # donus mesafesi SON noktadan eve
        self.assertAlmostEqual(a["donus_mesafesi_m"], 1111.9, delta=15)

    def test_irtifa_araligi(self):
        a = analyze_mission([YAKIN, ORTA, UZAK], home=HOME)
        self.assertEqual(a["min_irtifa_m"], 30.0)
        self.assertEqual(a["max_irtifa_m"], 50.0)


class GuvenlikUyarilariTest(unittest.TestCase):
    def test_dairesel_geofence_disi_hata_verir(self):
        a = analyze_mission(
            [YAKIN, UZAK], home=HOME,
            fence={"enabled": True, "radius_m": 1000},
        )
        hatalar = metinler(a, HATA)
        self.assertEqual(len(hatalar), 1, hatalar)
        self.assertIn("Waypoint 2", hatalar[0])
        self.assertIn("geofence", hatalar[0])

    def test_geofence_kapaliyken_kontrol_yapilmaz(self):
        a = analyze_mission(
            [UZAK], home=HOME, fence={"enabled": False, "radius_m": 100}
        )
        self.assertEqual(hata_sayisi(a), 0)

    def test_irtifa_limiti_asimi_hata_verir(self):
        a = analyze_mission(
            [(39.9210, 32.8600, 150.0)], home=HOME, fence={"alt_max_m": 100}
        )
        hatalar = metinler(a, HATA)
        self.assertEqual(len(hatalar), 1)
        self.assertIn("FENCE_ALT_MAX", hatalar[0])

    def test_sifir_irtifa_hata_verir(self):
        a = analyze_mission([(39.9210, 32.8600, 0.0)], home=HOME)
        self.assertTrue(any("sifir veya negatif" in m for m in metinler(a, HATA)))

    def test_poligon_geofence_disi_hata_verir(self):
        poligon = [
            (39.9190, 32.8590), (39.9190, 32.8610),
            (39.9260, 32.8610), (39.9260, 32.8590),
        ]
        a = analyze_mission(
            [YAKIN, UZAK], home=HOME, fence={"polygon": poligon}
        )
        hatalar = metinler(a, HATA)
        self.assertEqual(len(hatalar), 1, hatalar)
        self.assertIn("poligon", hatalar[0].lower())

    def test_cok_yakin_noktalar_uyari_verir(self):
        """Yanlis tiklama suphesi — hata degil, uyari."""
        a = analyze_mission(
            [(39.9250, 32.8600, 30.0), (39.92500, 32.86001, 30.0)], home=HOME
        )
        uyarilar = metinler(a, UYARI)
        self.assertTrue(any("yanlis tiklama" in u for u in uyarilar), uyarilar)
        self.assertEqual(hata_sayisi(a), 0)

    def test_home_bilinmiyorsa_uyari_verilir(self):
        a = analyze_mission([ORTA])
        self.assertTrue(any("Home" in u for u in metinler(a, UYARI)))

    def test_home_yokken_geofence_kontrolu_cokmez(self):
        a = analyze_mission([UZAK], fence={"enabled": True, "radius_m": 10})
        self.assertIsInstance(a["uyarilar"], list)

    def test_temiz_gorev_hata_uretmez(self):
        a = analyze_mission(
            [YAKIN, ORTA], home=HOME,
            fence={"enabled": True, "radius_m": 5000, "alt_max_m": 120},
        )
        self.assertEqual(hata_sayisi(a), 0, metinler(a, HATA))


class BicimlendirmeTest(unittest.TestCase):
    def test_sure_metni(self):
        self.assertEqual(sure_metni(0), "00:00")
        self.assertEqual(sure_metni(65), "01:05")
        self.assertEqual(sure_metni(3725), "1:02:05")

    def test_mesafe_metni(self):
        self.assertEqual(mesafe_metni(None), "--")
        self.assertEqual(mesafe_metni(450), "450 m")
        self.assertEqual(mesafe_metni(1500), "1.50 km")

    def test_ozet_metni(self):
        a = analyze_mission([ORTA], home=HOME)
        ozet = ozet_metni(a)
        self.assertIn("1 nokta", ozet)
        self.assertIn("km", ozet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
