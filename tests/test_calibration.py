"""
test_calibration.py
--------------------
ADIM 2 dogrulamasi: pusula ve ivmeolcer kalibrasyon sihirbazi.

Kontrol edilenler:
  - Dogru MAVLink komutlari, dogru parametrelerle gonderiliyor mu
  - MAG_CAL_PROGRESS / MAG_CAL_REPORT arayuze dogru yansiyor mu
  - Ivmeolcer 6 pozisyonu sirayla ve dogru kodlarla gonderiyor mu
  - STATUSTEXT ile adim senkronu calisiyor mu
  - ARM haldeyken kalibrasyon engelleniyor mu
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymavlink import mavutil

from core.drone_telemetry import ACCEL_CAL_POS_FAILED, ACCEL_CAL_POS_SUCCESS
from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump

M = mavutil.mavlink
CMD_START_MAG = M.MAV_CMD_DO_START_MAG_CAL
CMD_ACCEPT_MAG = M.MAV_CMD_DO_ACCEPT_MAG_CAL
CMD_CANCEL_MAG = M.MAV_CMD_DO_CANCEL_MAG_CAL
CMD_ACCEL_POS = M.MAV_CMD_ACCELCAL_VEHICLE_POS
CMD_PREFLIGHT = M.MAV_CMD_PREFLIGHT_CALIBRATION


class CalibrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected, "Sahte araca baglanilamadi"

    @classmethod
    def tearDownClass(cls):
        cls.win.worker.stop()
        cls.vehicle.stop()

    def setUp(self):
        self.vehicle.armed = False
        pump(0.6, until=lambda: not self.win.is_armed)
        # Onceki testten kalan STATUSTEXT / pozisyon istegi mesajlari
        # yeni sihirbaza sizarsa adim sayaci beklenmedik yere atlar.
        # Sihirbazi acmadan once boruyu bosaltiyoruz.
        pump(0.5)
        self.win.on_calibration_clicked()
        self.dialog = self.win.calibration_dialog
        self.assertIsNotNone(self.dialog, "Kalibrasyon sihirbazi acilmadi")

    def tearDown(self):
        if self.win.calibration_dialog is not None:
            self.win.calibration_dialog.close()
            pump(0.1)

    # ---------------- pusula ----------------

    def test_pusula_baslatma_komutu_autosave_kapali_gonderilir(self):
        """autosave=0 kritik: kotu bir kalibrasyon kullanici onaylamadan
        FC'ye kalici olarak yazilmamali."""
        onceki = len(self.vehicle.commands_of(CMD_START_MAG))
        self.dialog.btn_mag_start.click()
        pump(0.3)
        komutlar = self.vehicle.wait_for_command(CMD_START_MAG, onceki + 1)
        self.assertGreater(len(komutlar), onceki, "DO_START_MAG_CAL gonderilmedi")
        son = komutlar[-1]
        self.assertEqual(son.param1, 0, "param1=0 (tum pusulalar) olmali")
        self.assertEqual(son.param3, 0, "autosave acik gonderilmis")

    def test_pusula_ilerlemesi_arayuze_yansir(self):
        self.dialog.btn_mag_start.click()
        pump(0.3)
        self.vehicle.send_mag_cal_progress(42, cal_status=2)
        pump(4.0, until=lambda: self.dialog.mag_progress.value() == 42)
        self.assertEqual(self.dialog.mag_progress.value(), 42)
        self.assertIn("42", self.dialog.lbl_mag_durum.text())

    def test_basarili_rapor_kabul_butonunu_acar_ve_kaydeder(self):
        self.dialog.btn_mag_start.click()
        pump(0.3)
        self.assertFalse(self.dialog.btn_mag_accept.isEnabled())

        self.vehicle.send_mag_cal_report(cal_status=4, fitness=3.25)
        pump(4.0, until=lambda: self.dialog.btn_mag_accept.isEnabled())
        self.assertTrue(
            self.dialog.btn_mag_accept.isEnabled(), "Basarili raporda kabul butonu acilmadi"
        )
        self.assertEqual(self.dialog.mag_progress.value(), 100)

        onceki = len(self.vehicle.commands_of(CMD_ACCEPT_MAG))
        self.dialog.btn_mag_accept.click()
        pump(0.3)
        komutlar = self.vehicle.wait_for_command(CMD_ACCEPT_MAG, onceki + 1)
        self.assertGreater(len(komutlar), onceki, "DO_ACCEPT_MAG_CAL gonderilmedi")

    def test_basarisiz_rapor_kabul_butonunu_acmaz(self):
        self.dialog.btn_mag_start.click()
        pump(0.3)
        self.vehicle.send_mag_cal_report(cal_status=6)  # BAD_ORIENTATION
        pump(4.0, until=lambda: "yonelim" in self.dialog.lbl_mag_durum.text().lower())
        self.assertFalse(self.dialog.btn_mag_accept.isEnabled())
        self.assertIn("yonelim", self.dialog.lbl_mag_durum.text().lower())

    def test_iptal_komutu_gonderilir(self):
        self.dialog.btn_mag_start.click()
        pump(0.3)
        onceki = len(self.vehicle.commands_of(CMD_CANCEL_MAG))
        self.dialog.btn_mag_cancel.click()
        pump(0.3)
        komutlar = self.vehicle.wait_for_command(CMD_CANCEL_MAG, onceki + 1)
        self.assertGreater(len(komutlar), onceki, "DO_CANCEL_MAG_CAL gonderilmedi")

    # ---------------- ivmeolcer ----------------

    def test_ivmeolcer_baslatma_param5_1_gonderir(self):
        onceki = len(self.vehicle.commands_of(CMD_PREFLIGHT))
        self.dialog.btn_accel_start.click()
        pump(0.3)
        komutlar = self.vehicle.wait_for_command(CMD_PREFLIGHT, onceki + 1)
        self.assertGreater(len(komutlar), onceki, "PREFLIGHT_CALIBRATION gonderilmedi")
        self.assertEqual(komutlar[-1].param5, 1, "param5=1 (tam accel cal) olmali")

    def test_alti_pozisyon_sirayla_dogru_kodlarla_gonderilir(self):
        self.dialog.btn_accel_start.click()
        pump(0.3)
        onceki = len(self.vehicle.commands_of(CMD_ACCEL_POS))
        for _ in range(6):
            self.dialog.btn_accel_next.click()
            pump(0.15)
        komutlar = self.vehicle.wait_for_command(CMD_ACCEL_POS, onceki + 6)
        kodlar = [int(m.param1) for m in komutlar[onceki:]]
        self.assertEqual(
            kodlar, [1, 2, 3, 4, 5, 6],
            "Pozisyon kodlari LEVEL,LEFT,RIGHT,NOSEDOWN,NOSEUP,BACK sirasinda olmali",
        )
        self.assertFalse(self.dialog.btn_accel_next.isEnabled())

    def test_statustext_adimi_senkronlar(self):
        """FC bir pozisyonu tekrar isterse sihirbaz o adima geri doner."""
        self.dialog.btn_accel_start.click()
        pump(0.3)
        self.dialog.btn_accel_next.click()  # 1. adim gonderildi, sira 2. adimda
        pump(0.15)
        self.assertEqual(self.dialog._accel_adim, 1)

        self.vehicle.send_statustext("Place vehicle nose DOWN and press any key")
        pump(4.0, until=lambda: self.dialog._accel_adim == 3)
        self.assertEqual(self.dialog._accel_adim, 3, "NOSEDOWN adimina senkronlanmadi")

    def test_fc_pozisyon_istegi_adimi_senkronlar(self):
        """ASIL kanal: FC istedigi pozisyonu COMMAND_LONG /
        ACCELCAL_VEHICLE_POS ile bildirir. ArduPilot ilk yanitimizdan sonra
        'Place vehicle ...' STATUSTEXT'lerini KESER, bu yuzden sihirbaz
        yalnizca STATUSTEXT'e guvenemez."""
        self.dialog.btn_accel_start.click()
        pump(0.3)
        self.assertEqual(self.dialog._accel_adim, 0)

        self.vehicle.send_accel_cal_position_request(3)  # SAG YAN
        pump(4.0, until=lambda: self.dialog._accel_adim == 2)
        self.assertEqual(
            self.dialog._accel_adim, 2, "FC pozisyon istegi adimi senkronlamadi"
        )
        self.assertTrue(self.dialog.btn_accel_next.isEnabled())

    def test_fc_basari_kodu_sihirbazi_bitirir(self):
        self.dialog.btn_accel_start.click()
        pump(0.3)
        self.vehicle.send_accel_cal_position_request(ACCEL_CAL_POS_SUCCESS)
        pump(4.0, until=lambda: not self.dialog._accel_calisiyor)
        self.assertFalse(self.dialog._accel_calisiyor)
        self.assertIn("BASARILI", self.dialog.lbl_accel_talimat.text())

    def test_fc_hata_kodu_sihirbazi_bitirir(self):
        """SITL'de gercekten gorulen durum: arac fiziksel olarak
        cevrilemedigi icin FC 16777216 (FAILED) gonderir."""
        self.dialog.btn_accel_start.click()
        pump(0.3)
        self.vehicle.send_accel_cal_position_request(ACCEL_CAL_POS_FAILED)
        pump(4.0, until=lambda: not self.dialog._accel_calisiyor)
        self.assertFalse(self.dialog._accel_calisiyor)
        self.assertIn("BASARISIZ", self.dialog.lbl_accel_talimat.text())

    def test_basari_mesaji_sihirbazi_bitirir(self):
        self.dialog.btn_accel_start.click()
        pump(0.3)
        self.vehicle.send_statustext("Calibration successful")
        pump(4.0, until=lambda: not self.dialog._accel_calisiyor)
        self.assertFalse(self.dialog._accel_calisiyor)
        self.assertIn("BASARILI", self.dialog.lbl_accel_talimat.text())

    # ---------------- guvenlik ----------------

    def test_arm_haldeyken_kalibrasyon_engellenir(self):
        self.vehicle.armed = True
        self.assertTrue(pump(6.0, until=lambda: self.win.is_armed), "ARM yansimadi")
        pump(0.3)

        self.assertFalse(
            self.dialog.btn_mag_start.isEnabled(), "ARM iken pusula butonu aktif kaldi"
        )
        self.assertFalse(self.dialog.btn_accel_start.isEnabled())
        self.assertTrue(self.dialog.lbl_uyari.isVisible() or self.dialog.isHidden())

        # Sinyal dogrudan tetiklense bile komut gonderilmemeli.
        onceki = len(self.vehicle.commands_of(CMD_START_MAG))
        self.win._kalibrasyon_komutu("start_mag_cal", "test")
        pump(0.5)
        self.assertEqual(
            len(self.vehicle.commands_of(CMD_START_MAG)), onceki,
            "ARM haldeyken kalibrasyon komutu gonderildi",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
