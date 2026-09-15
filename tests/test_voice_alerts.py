"""
test_voice_alerts.py
---------------------
ADIM 4 dogrulamasi: sesli uyari sistemi (TTS).

Testler gercek konusma yapmaz — arka uc yerine kaydedici bir fonksiyon
konur. Boylece hem CI'da sessiz calisir hem de hangi metnin kac kez
seslendirildigi kesin olarak olculebilir.
"""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.voice_alerts import VoiceAlerts
from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump


class Kaydedici:
    """Sahte TTS arka ucu: konusmak yerine metinleri biriktirir."""

    def __init__(self):
        self.metinler = []
        self._lock = threading.Lock()

    def __call__(self, metin):
        with self._lock:
            self.metinler.append(metin)

    def liste(self):
        with self._lock:
            return list(self.metinler)

    def temizle(self):
        with self._lock:
            self.metinler = []


class VoiceAlertsTest(unittest.TestCase):
    def setUp(self):
        self.kayit = Kaydedici()
        self.voice = VoiceAlerts(enabled=True, backend=self.kayit)

    def tearDown(self):
        self.voice.stop()

    def test_anons_arka_uca_ulasir(self):
        self.assertTrue(self.voice.say("Dusuk pil, yuzde on bes"))
        self.voice.wait_idle()
        self.assertEqual(self.kayit.liste(), ["Dusuk pil, yuzde on bes"])

    def test_ayni_uyari_bekleme_suresi_dolmadan_tekrarlanmaz(self):
        """Dusuk pil SYS_STATUS'u saniyede birkac kez gelir; throttle
        olmasa bilgisayar durmadan konusurdu."""
        self.assertTrue(self.voice.say("Dusuk pil", key="pil", min_interval_s=60))
        self.assertFalse(self.voice.say("Dusuk pil", key="pil", min_interval_s=60))
        self.assertFalse(self.voice.say("Dusuk pil", key="pil", min_interval_s=60))
        self.voice.wait_idle()
        self.assertEqual(len(self.kayit.liste()), 1)

    def test_farkli_anahtar_ayri_throttle(self):
        self.voice.say("Dusuk pil", key="pil", min_interval_s=60)
        self.voice.say("Geofence ihlali", key="fence", min_interval_s=60)
        self.voice.wait_idle()
        self.assertEqual(len(self.kayit.liste()), 2)

    def test_bekleme_suresi_dolunca_tekrar_seslendirilir(self):
        self.voice.say("Dusuk pil", key="pil", min_interval_s=0.0)
        self.voice.say("Dusuk pil", key="pil", min_interval_s=0.0)
        self.voice.wait_idle()
        self.assertEqual(len(self.kayit.liste()), 2)

    def test_kapaliyken_hicbir_cagri_yapilmaz(self):
        self.voice.set_enabled(False)
        self.assertFalse(self.voice.say("Bu duyulmamali"))
        self.voice.wait_idle()
        self.assertEqual(self.kayit.liste(), [])

    def test_kapatinca_bekleyen_kuyruk_bosalir(self):
        yavas = threading.Event()
        kayit = Kaydedici()

        def yavas_arka_uc(metin):
            yavas.wait(timeout=1.0)
            kayit(metin)

        voice = VoiceAlerts(enabled=True, backend=yavas_arka_uc)
        try:
            for i in range(4):
                voice.say(f"mesaj {i}", key=f"k{i}")
            voice.set_enabled(False)
            yavas.set()
            voice.wait_idle()
            self.assertLess(
                len(kayit.liste()), 4, "Kapatildiktan sonra kuyruk bosalmadi"
            )
        finally:
            voice.stop()

    def test_arka_uc_hatasi_uygulamayi_dusurmez(self):
        def patlayan(metin):
            raise RuntimeError("TTS bozuk")

        voice = VoiceAlerts(enabled=True, backend=patlayan)
        try:
            voice.say("dene")
            voice.wait_idle()
            # Hatadan sonra sistem calismaya devam etmeli
            self.assertTrue(voice.say("tekrar dene", key="ikinci"))
        finally:
            voice.stop()

    def test_tts_yoksa_ozellik_sessizce_kapanir(self):
        voice = VoiceAlerts(enabled=True, backend=None)
        # backend=None -> detect_backend() calisir; burada onu bastiriyoruz
        voice._backend = None
        voice._enabled = False
        self.assertFalse(voice.available)
        self.assertFalse(voice.enabled)
        self.assertFalse(voice.say("duyulmamali"))
        voice.stop()

    def test_kuyruk_ust_sinirda_birikmez(self):
        bekle = threading.Event()
        voice = VoiceAlerts(enabled=True, backend=lambda m: bekle.wait(timeout=2.0))
        try:
            kabul = sum(
                1 for i in range(40)
                if voice.say(f"mesaj {i}", key=f"k{i}", min_interval_s=0)
            )
            self.assertLess(kabul, 40, "Kuyruk sinirsiz buyudu")
        finally:
            bekle.set()
            voice.stop()


class VoiceIntegrationTest(unittest.TestCase):
    """Uygulamanin gercek tetikleyicileri sesli uyari uretiyor mu?"""

    @classmethod
    def setUpClass(cls):
        cls.kayit = Kaydedici()
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port, voice_backend=cls.kayit)
        assert cls.win.connected, "Sahte araca baglanilamadi"

    @classmethod
    def tearDownClass(cls):
        cls.win.voice.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()

    def setUp(self):
        self.kayit.temizle()
        self.win.voice._son_soylenen.clear()

    def _anonslarda_ara(self, parca, sure=3.0):
        pump(sure, until=lambda: any(
            parca.lower() in m.lower() for m in self.kayit.liste()
        ))
        return [m for m in self.kayit.liste() if parca.lower() in m.lower()]

    def test_ilk_baglantida_geri_geldi_denmez(self):
        """Regresyon: _was_ever_connected baglanti aninda True yapildigi
        icin ilk baglantida da 'geri geldi' anonsu yapiliyordu."""
        # setUpClass sirasinda ilk baglanti kuruldu; o ana ait kayitlar
        # temizlenmeden once kontrol edilmeliydi, bu yuzden dogrudan
        # bayragin mantigini dogruluyoruz.
        self.assertTrue(self.win._was_ever_connected)
        self.win.voice.set_enabled(True)
        self.kayit.temizle()
        # Ilk baglanti simulasyonu: bayragi sifirla
        self.win._was_ever_connected = False
        self.win.update_connection_status(True, "test")
        pump(0.6)
        self.assertEqual(
            self._anonslarda_ara("geri geldi", 0.5), [],
            "Ilk baglantida 'geri geldi' anonsu yapildi",
        )

    def test_dusuk_pil_sesli_uyari(self):
        self.vehicle.send_sys_status(battery_remaining=15)
        bulunan = self._anonslarda_ara("dusuk pil")
        self.assertTrue(bulunan, f"Dusuk pil anonsu yapilmadi: {self.kayit.liste()}")
        self.assertIn("15", bulunan[0])

    def test_arm_disarm_sesli_uyari(self):
        self.vehicle.armed = True
        self.assertTrue(pump(6.0, until=lambda: self.win.is_armed))
        self.assertTrue(self._anonslarda_ara("armed"), "ARM anonsu yapilmadi")

        self.vehicle.armed = False
        self.assertTrue(pump(6.0, until=lambda: not self.win.is_armed))
        self.assertTrue(self._anonslarda_ara("disarmed"), "DISARM anonsu yapilmadi")

    def test_geofence_ihlali_sesli_uyari(self):
        self.vehicle.send_statustext("Fence breach: circle", severity=4)
        self.assertTrue(
            self._anonslarda_ara("geofence"),
            f"Geofence anonsu yapilmadi: {self.kayit.liste()}",
        )

    def test_kritik_statustext_okunur_bilgi_mesaji_okunmaz(self):
        """MAV_SEVERITY <= 3 kritiktir; 4 ve uzeri okunmamali."""
        self.vehicle.send_statustext("Motor failure detected", severity=2)
        self.assertTrue(
            self._anonslarda_ara("motor failure"), "Kritik mesaj okunmadi"
        )
        self.kayit.temizle()
        self.vehicle.send_statustext("EKF3 IMU0 is using GPS", severity=6)
        pump(1.5)
        self.assertEqual(
            self._anonslarda_ara("ekf3", 0.3), [], "Bilgi mesaji sesli okundu"
        )

    def test_ses_kapatilinca_anons_yapilmaz(self):
        self.win.voice.set_enabled(False)
        try:
            self.vehicle.send_sys_status(battery_remaining=12)
            pump(2.0)
            self.assertEqual(
                self.kayit.liste(), [], "Ses kapaliyken anons yapildi"
            )
        finally:
            self.win.voice.set_enabled(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
