"""
test_exporters.py
------------------
ADIM 3 dogrulamasi: .waypoints (QGC WPL 110) ve .kml disa aktarma.

.waypoints formati baska GCS yazilimlari tarafindan okunacagi icin satir
duzeni birebir dogrulanir; KML ise gercekten ayristirilabilir XML olmali.
"""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exporters import (
    WAYPOINTS_HEADER,
    flight_log_to_kml,
    mission_to_kml,
    mission_to_waypoints,
    parse_waypoints,
)

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

GOREV = [
    (39.925533, 32.866287, 30.0),
    (39.930000, 32.870000, 45.5),
    (39.935000, 32.875000, 20.0),
]


class WaypointsTest(unittest.TestCase):
    def test_baslik_ve_satir_sayisi(self):
        metin = mission_to_waypoints(GOREV)
        satirlar = metin.strip().splitlines()
        self.assertEqual(satirlar[0], WAYPOINTS_HEADER)
        # 1 baslik + 1 home + 3 waypoint
        self.assertEqual(len(satirlar), 1 + 1 + len(GOREV))

    def test_home_satiri_index_0_ve_frame_0(self):
        """ArduPilot'ta satir 0 home'dur, mutlak cerceve (frame 0) kullanir
        ve navigasyon icin yurutulmez."""
        satirlar = mission_to_waypoints(GOREV, home=(40.0, 33.0)).strip().splitlines()
        alanlar = satirlar[1].split("\t")
        self.assertEqual(alanlar[0], "0", "home satiri index 0 olmali")
        self.assertEqual(alanlar[1], "1", "home satiri current=1 olmali")
        self.assertEqual(alanlar[2], "0", "home satiri frame 0 (mutlak) olmali")
        self.assertAlmostEqual(float(alanlar[8]), 40.0, places=6)
        self.assertAlmostEqual(float(alanlar[9]), 33.0, places=6)

    def test_gercek_waypointler_frame_3_ve_1den_baslar(self):
        satirlar = mission_to_waypoints(GOREV).strip().splitlines()
        for i, satir in enumerate(satirlar[2:], start=1):
            alanlar = satir.split("\t")
            self.assertEqual(alanlar[0], str(i))
            self.assertEqual(alanlar[2], "3", "waypoint frame 3 (relative alt) olmali")
            self.assertEqual(alanlar[3], "16", "komut 16 (NAV_WAYPOINT) olmali")
            self.assertEqual(alanlar[11], "1", "autocontinue 1 olmali")
            self.assertEqual(len(alanlar), 12, "QGC WPL satiri 12 alan icerir")

    def test_home_verilmezse_ilk_waypoint_kullanilir(self):
        satirlar = mission_to_waypoints(GOREV).strip().splitlines()
        alanlar = satirlar[1].split("\t")
        self.assertAlmostEqual(float(alanlar[8]), GOREV[0][0], places=6)

    def test_yazilan_dosya_geri_okunabilir(self):
        """Disa aktarma/geri okuma turu: koordinatlar ve irtifalar korunmali."""
        geri = parse_waypoints(mission_to_waypoints(GOREV))
        self.assertEqual(len(geri), len(GOREV))
        for beklenen, gelen in zip(GOREV, geri):
            self.assertAlmostEqual(beklenen[0], gelen[0], places=6)
            self.assertAlmostEqual(beklenen[1], gelen[1], places=6)
            self.assertAlmostEqual(beklenen[2], gelen[2], places=3)

    def test_bos_gorev_hata_verir(self):
        with self.assertRaises(ValueError):
            mission_to_waypoints([])

    def test_gecersiz_dosya_reddedilir(self):
        with self.assertRaises(ValueError):
            parse_waypoints("rastgele metin\n1\t2\t3\n")


class KmlTest(unittest.TestCase):
    def test_gorev_kml_gecerli_xml(self):
        kok = ET.fromstring(mission_to_kml(GOREV, ad="Test Gorevi"))
        self.assertTrue(kok.tag.endswith("kml"))
        ad = kok.find(".//kml:Document/kml:name", KML_NS)
        self.assertEqual(ad.text, "Test Gorevi")

    def test_koordinat_sirasi_boylam_enlem_irtifa(self):
        """KML'de sira lon,lat,alt'tir — lat,lon yazmak rotayi dunyanin
        bambaska bir yerine tasir."""
        kok = ET.fromstring(mission_to_kml(GOREV))
        koord = kok.find(".//kml:LineString/kml:coordinates", KML_NS).text.split()
        self.assertEqual(len(koord), len(GOREV))
        lon, lat, alt = koord[0].split(",")
        self.assertAlmostEqual(float(lon), GOREV[0][1], places=6)
        self.assertAlmostEqual(float(lat), GOREV[0][0], places=6)
        self.assertAlmostEqual(float(alt), GOREV[0][2], places=2)

    def test_her_waypoint_icin_isaretci(self):
        kok = ET.fromstring(mission_to_kml(GOREV))
        noktalar = kok.findall(".//kml:Placemark/kml:Point", KML_NS)
        self.assertEqual(len(noktalar), len(GOREV))

    def test_irtifa_modu_relative(self):
        kok = ET.fromstring(mission_to_kml(GOREV))
        mod = kok.find(".//kml:LineString/kml:altitudeMode", KML_NS)
        self.assertEqual(mod.text, "relativeToGround")


class FlightLogKmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.tmp.name, "flight_test.csv")
        with open(self.csv_path, "w", encoding="utf-8") as f:
            f.write("timestamp,lat,lon,alt,groundspeed,heading,battery,mode,armed\n")
            # GPS kilidi oncesi satir (0,0) — atlanmali
            f.write("2026-09-15 10:00:00,0.0,0.0,0.0,0,0,100,GUIDED,True\n")
            f.write("2026-09-15 10:00:01,39.925533,32.866287,10.0,3.2,90,99,GUIDED,True\n")
            f.write("2026-09-15 10:00:02,39.926000,32.867000,20.0,5.1,95,98,AUTO,True\n")
            # bozuk satir — atlanmali
            f.write("2026-09-15 10:00:03,,,,,,,,\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_gecerli_kml_uretir(self):
        kok = ET.fromstring(flight_log_to_kml(self.csv_path))
        self.assertTrue(kok.tag.endswith("kml"))

    def test_gecersiz_satirlar_atlanir(self):
        kok = ET.fromstring(flight_log_to_kml(self.csv_path))
        koord = kok.find(".//kml:LineString/kml:coordinates", KML_NS).text.split()
        self.assertEqual(len(koord), 2, "0,0 ve bozuk satirlar atlanmaliydi")

    def test_kalkis_ve_inis_isaretcileri(self):
        kok = ET.fromstring(flight_log_to_kml(self.csv_path))
        adlar = [p.find("kml:name", KML_NS).text
                 for p in kok.findall(".//kml:Placemark", KML_NS)]
        self.assertIn("Kalkis", adlar)
        self.assertIn("Inis", adlar)

    def test_konum_olmayan_kayit_hata_verir(self):
        bos = os.path.join(self.tmp.name, "bos.csv")
        with open(bos, "w", encoding="utf-8") as f:
            f.write("timestamp,lat,lon,alt,groundspeed,heading,battery,mode,armed\n")
        with self.assertRaises(ValueError):
            flight_log_to_kml(bos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
