"""
test_mavlink_surumu.py
-----------------------
Regresyon koruması: uygulama MAVLink 2 diyalektini kullanmali.

BULUNAN SORUN
-------------
pymavlink, MAVLINK20 ortam degiskeni ayarlanmamissa MAVLink 1
diyalektini yukler. MAVLink 1 tanimlarinda gorev mesajlarinin
`mission_type` alani YOKTUR ve fonksiyon imzalarinda son parametre
`force_mavlink1`'dir:

    v1:  mission_clear_all_send(sys, comp, force_mavlink1)
    v2:  mission_clear_all_send(sys, comp, mission_type, force_mavlink1)

Kod v2 imzasina gore yazilmisti. v1 altinda calisirken
`mission_clear_all_send(..., MAV_MISSION_TYPE_FENCE)` cagrisi, fence
tipini sessizce `force_mavlink1` parametresine geciriyordu; yani
mission_type HIC GONDERILMIYORDU.

SITL ile olculen gercek etki: ArduPilot, gelen item'in komut kimliginden
(MAV_CMD_NAV_FENCE_* / MAV_CMD_NAV_RALLY_POINT) dogru tabloyu cikarabildigi
icin fence yine de FENCE tablosuna ulasiyordu ve ucus gorevi bozulmuyordu.
Yani sorun VERI KAYBINA yol acmiyordu — ama davranis, otopilotun
toleransina bagliydi: protokolun acikca soylemesi gereken bilgi
gonderilmiyordu ve baska bir otopilot/surum bunu reddedebilirdi.

MAVLink 2'ye gecince mission_type gercekten iletiliyor (rally item'larinda
mission_type=2 olarak dogrulandi) ve davranis tanimli hale geliyor.
ArduPilot 4.x zaten MAVLink 2 konusur.
"""

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mavlink_env  # noqa: F401  (diyalekti v2'ye ayarlar)
from core.mavlink_env import mavlink2_aktif

from pymavlink import mavutil

GOREV_FONKSIYONLARI = [
    "mission_item_int_send",
    "mission_count_send",
    "mission_clear_all_send",
    "mission_request_list_send",
    "mission_request_int_send",
]


class MavlinkSurumuTest(unittest.TestCase):
    def test_mavlink2_diyalekti_yuklu(self):
        self.assertTrue(
            mavlink2_aktif(),
            f"MAVLink 1 diyalekti yuklu: {mavutil.mavlink.__name__}",
        )
        self.assertIn("v20", mavutil.mavlink.__name__)

    def test_wire_protokolu_2(self):
        self.assertEqual(mavutil.mavlink.WIRE_PROTOCOL_VERSION, "2.0")

    def test_gorev_fonksiyonlari_mission_type_kabul_ediyor(self):
        """Asil regresyon: bu parametre yoksa fence/rally yanlis tabloya
        yazilir."""
        for ad in GOREV_FONKSIYONLARI:
            imza = inspect.signature(getattr(mavutil.mavlink.MAVLink, ad))
            self.assertIn(
                "mission_type", imza.parameters,
                f"{ad} mission_type kabul etmiyor — MAVLink 1 yuklu",
            )

    def test_mission_item_int_mesajinda_mission_type_alani_var(self):
        self.assertIn(
            "mission_type",
            mavutil.mavlink.MAVLink_mission_item_int_message.fieldnames,
        )

    def test_mission_type_force_mavlink1_den_once_gelir(self):
        """Kodun konumsal (positional) cagrilari bu siraya dayaniyor."""
        for ad in GOREV_FONKSIYONLARI:
            parametreler = list(
                inspect.signature(getattr(mavutil.mavlink.MAVLink, ad)).parameters
            )
            self.assertLess(
                parametreler.index("mission_type"),
                parametreler.index("force_mavlink1"),
                f"{ad} parametre sirasi beklenenden farkli",
            )

    def test_fence_ve_rally_tipleri_farkli(self):
        """Ayni degere sahip olsalardi yanlis tablo sessizce yazilirdi."""
        self.assertNotEqual(
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
        )
        self.assertNotEqual(
            mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
            mavutil.mavlink.MAV_MISSION_TYPE_RALLY,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
