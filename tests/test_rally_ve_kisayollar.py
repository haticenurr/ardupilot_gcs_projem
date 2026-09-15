"""
test_rally_ve_kisayollar.py
----------------------------
ADIM 10 dogrulamasi: acil inis (rally) noktalari ve klavye kisayollari.

Rally noktalari failsafe davranisini degistirir — ArduPilot RTL yerine en
yakin rally noktasina gidebilir. Bu yuzden yuklenen koordinatlarin
birebir dogru gitmesi kritiktir.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymavlink import mavutil

from core.drone_telemetry import DroneTelemetry
from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump

RALLY = [
    (39.9250, 32.8650, 30.0),
    (39.9280, 32.8700, 45.0),
]


class RallyProtokolTest(unittest.TestCase):
    """MAVLink katmani: rally noktalari dogru tip ve komutla gidiyor mu?"""

    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.mission_protocol = True
        cls.vehicle.start()
        cls.drone = DroneTelemetry(f"udpin:127.0.0.1:{cls.vehicle.port}")

    @classmethod
    def tearDownClass(cls):
        cls.drone.close()
        cls.vehicle.stop()

    def test_yukleme_basarili(self):
        ok, mesaj = self.drone.upload_rally_points(RALLY)
        self.assertTrue(ok, mesaj)
        self.assertIn("rally", mesaj.lower())

    def test_dogru_mission_type_ve_komut_kullanilir(self):
        """Rally, gorev veya fence ile karistirilirsa FC yanlis tabloyu
        gunceller."""
        self.drone.upload_rally_points(RALLY)
        item_ler = [
            m for m in self.vehicle.messages_of("MISSION_ITEM_INT")
            if int(getattr(m, "mission_type", 0))
            == mavutil.mavlink.MAV_MISSION_TYPE_RALLY
        ]
        self.assertGreaterEqual(len(item_ler), len(RALLY))
        for m in item_ler[-len(RALLY):]:
            self.assertEqual(
                int(m.command), mavutil.mavlink.MAV_CMD_NAV_RALLY_POINT
            )

    def test_gidis_donus_koordinatlari_korur(self):
        ok, _ = self.drone.upload_rally_points(RALLY)
        self.assertTrue(ok)
        ok, mesaj, geri = self.drone.download_rally_points()
        self.assertTrue(ok, mesaj)
        self.assertEqual(len(geri), len(RALLY))
        for beklenen, gelen in zip(RALLY, geri):
            self.assertAlmostEqual(beklenen[0], gelen[0], places=6)
            self.assertAlmostEqual(beklenen[1], gelen[1], places=6)
            self.assertAlmostEqual(beklenen[2], gelen[2], places=2)

    def test_bos_liste_reddedilir(self):
        ok, mesaj = self.drone.upload_rally_points([])
        self.assertFalse(ok)
        self.assertIn("en az 1", mesaj.lower())

    def test_silme_calisir(self):
        self.drone.upload_rally_points(RALLY)
        ok, mesaj = self.drone.clear_rally_points()
        self.assertTrue(ok, mesaj)
        ok, _mesaj, geri = self.drone.download_rally_points()
        self.assertTrue(ok)
        self.assertEqual(geri, [])


class RallyArayuzTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.mission_protocol = True
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected

    @classmethod
    def tearDownClass(cls):
        cls.win.voice.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()

    def setUp(self):
        self.win.on_rally_clear_requested()
        self.win.on_rally_draw_toggled(False)

    def test_cizim_kapaliyken_tiklama_nokta_eklemez(self):
        self.win.on_rally_point_added(39.925, 32.865)
        self.assertEqual(self.win.rally_points, [])

    def test_nokta_ekleme_ve_geri_alma(self):
        self.win.on_rally_draw_toggled(True)
        self.win.on_rally_point_added(39.925, 32.865)
        self.win.on_rally_point_added(39.928, 32.870)
        self.assertEqual(len(self.win.rally_points), 2)
        self.assertIn("2 nokta", self.win.safety_panel.rally_point_label.text())

        self.win.on_rally_undo_requested()
        self.assertEqual(len(self.win.rally_points), 1)

    def test_eklenen_nokta_kalkis_irtifasini_alir(self):
        self.win.spin_takeoff_alt.setValue(35)
        self.win.on_rally_draw_toggled(True)
        self.win.on_rally_point_added(39.925, 32.865)
        self.assertEqual(self.win.rally_points[0][2], 35.0)

    def test_rally_cizimi_poligon_cizimini_kapatir(self):
        """Ayni anda iki harita tiklama modu acik kalirsa nokta yanlis
        listeye duser."""
        self.win.on_polygon_draw_toggled(True)
        self.assertTrue(self.win.polygon_edit_active)
        self.win.on_rally_draw_toggled(True)
        self.assertFalse(self.win.polygon_edit_active)
        self.assertTrue(self.win.rally_edit_active)

    def test_nokta_yokken_yukleme_engellenir(self):
        onceki = len(self.vehicle.messages_of("MISSION_COUNT"))
        self.win.on_rally_upload_requested()
        pump(0.6)
        self.assertEqual(
            len(self.vehicle.messages_of("MISSION_COUNT")), onceki,
            "Bos rally listesi FC'ye gonderildi",
        )

    def test_yukleme_fcye_ulasir(self):
        self.win.on_rally_draw_toggled(True)
        self.win.on_rally_point_added(39.9250, 32.8650)
        self.win.on_rally_point_added(39.9280, 32.8700)
        self.win.on_rally_upload_requested()
        gelen = self.vehicle.wait_for("MISSION_ITEM_INT", 2, timeout=6)
        rally_item = [
            m for m in gelen
            if int(getattr(m, "mission_type", 0))
            == mavutil.mavlink.MAV_MISSION_TYPE_RALLY
        ]
        self.assertGreaterEqual(len(rally_item), 2)


class KisayolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)

    @classmethod
    def tearDownClass(cls):
        cls.win.voice.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()

    def test_beklenen_kisayollar_tanimli(self):
        diziler = {k.key().toString() for k in self.win._shortcuts}
        for beklenen in ("Ctrl+R", "Ctrl+L", "Ctrl+Shift+D", "Ctrl+K", "Ctrl+E"):
            self.assertIn(beklenen, diziler)

    def test_disarm_kisayolu_disarm_haldeyken_is_yapmaz(self):
        """ARM etmeyi kisayola baglamak kazara motor calistirma riski
        dogurur; kisayol yalnizca ARM durumdayken is yapmali."""
        self.vehicle.armed = False
        pump(4.0, until=lambda: not self.win.is_armed)
        cagrildi = []
        orijinal = self.win.on_arm_disarm_clicked
        self.win.on_arm_disarm_clicked = lambda: cagrildi.append(1)
        try:
            self.win._shortcut_disarm()
        finally:
            self.win.on_arm_disarm_clicked = orijinal
        self.assertEqual(cagrildi, [], "DISARM kisayolu bos yere calisti")

    def test_disarm_kisayolu_arm_haldeyken_onay_akisini_tetikler(self):
        self.vehicle.armed = True
        self.assertTrue(pump(6.0, until=lambda: self.win.is_armed))
        cagrildi = []
        orijinal = self.win.on_arm_disarm_clicked
        self.win.on_arm_disarm_clicked = lambda: cagrildi.append(1)
        try:
            self.win._shortcut_disarm()
        finally:
            self.win.on_arm_disarm_clicked = orijinal
            self.vehicle.armed = False
            pump(4.0, until=lambda: not self.win.is_armed)
        self.assertEqual(len(cagrildi), 1)

    def test_kisayollar_ipuclarinda_yazili(self):
        self.assertIn("Ctrl+R", self.win.btn_rtl.toolTip())
        self.assertIn("Ctrl+L", self.win.btn_land.toolTip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
