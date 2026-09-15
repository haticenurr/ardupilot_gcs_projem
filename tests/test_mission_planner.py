"""
test_mission_planner.py
------------------------
ADIM 7 dogrulamasi: otomatik rota uretimi geometrisi.

Testler saf matematige bakar — Qt, MAVLink veya arac gerekmez.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mission_planner import (
    centroid,
    expanding_square,
    point_in_polygon,
    polygon_area_m2,
    route_length_m,
    spacing_from_camera,
    survey_grid,
    to_latlon,
    to_local,
)

# Ankara yakininda, kenarlari yaklasik 670 m x 855 m olan bir dortgen.
KARE = [
    (39.9200, 32.8600),
    (39.9200, 32.8700),
    (39.9260, 32.8700),
    (39.9260, 32.8600),
]

# Icbukey (L seklinde) alan — tarama hattinin bir satirda iki parcaya
# bolunmesi gereken durum.
L_ALAN = [
    (39.9200, 32.8600),
    (39.9200, 32.8700),
    (39.9230, 32.8700),
    (39.9230, 32.8650),
    (39.9260, 32.8650),
    (39.9260, 32.8600),
]


def yerel_kutu(polygon):
    lat0, lon0 = centroid(polygon)
    noktalar = [to_local(p[0], p[1], lat0, lon0) for p in polygon]
    xs = [p[0] for p in noktalar]
    ys = [p[1] for p in noktalar]
    return (lat0, lon0), (min(xs), max(xs), min(ys), max(ys))


class IzdusumTest(unittest.TestCase):
    def test_gidis_donus_ayni_noktayi_verir(self):
        lat0, lon0 = 39.925, 32.866
        for lat, lon in [(39.93, 32.87), (39.91, 32.85), (lat0, lon0)]:
            x, y = to_local(lat, lon, lat0, lon0)
            geri_lat, geri_lon = to_latlon(x, y, lat0, lon0)
            self.assertAlmostEqual(lat, geri_lat, places=9)
            self.assertAlmostEqual(lon, geri_lon, places=9)

    def test_kuzeye_gitmek_y_artirir(self):
        x, y = to_local(39.935, 32.866, 39.925, 32.866)
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertGreater(y, 1000)  # 0.01 derece enlem ~ 1.1 km

    def test_dogu_yonu_x_artirir(self):
        x, y = to_local(39.925, 32.876, 39.925, 32.866)
        self.assertGreater(x, 0)
        self.assertAlmostEqual(y, 0.0, places=6)


class KameraAraligiTest(unittest.TestCase):
    def test_bilinen_deger(self):
        """100 m irtifa, 90 derece FOV, ortusme yok:
        yer genisligi = 2 * 100 * tan(45) = 200 m."""
        self.assertAlmostEqual(spacing_from_camera(100, 90, 0.0), 200.0, places=6)

    def test_ortusme_araligi_daraltir(self):
        tam = spacing_from_camera(100, 90, 0.0)
        ortusmeli = spacing_from_camera(100, 90, 0.3)
        self.assertAlmostEqual(ortusmeli, tam * 0.7, places=6)

    def test_irtifa_ile_dogru_orantili(self):
        self.assertAlmostEqual(
            spacing_from_camera(200, 60, 0.2),
            2 * spacing_from_camera(100, 60, 0.2),
            places=6,
        )

    def test_gecersiz_degerler_reddedilir(self):
        for args in [(0, 90, 0.2), (-10, 90, 0.2), (100, 0, 0.2),
                     (100, 200, 0.2), (100, 90, 1.0), (100, 90, -0.1)]:
            with self.assertRaises(ValueError, msg=f"kabul edildi: {args}"):
                spacing_from_camera(*args)


class PoligonTest(unittest.TestCase):
    def test_alan_yaklasik_dogru(self):
        """Dortgenin kenarlari ~667 m ve ~855 m -> ~570.000 m2."""
        alan = polygon_area_m2(KARE)
        self.assertGreater(alan, 500_000)
        self.assertLess(alan, 640_000)

    def test_ic_ve_dis_nokta(self):
        self.assertTrue(point_in_polygon(39.9230, 32.8650, KARE))
        self.assertFalse(point_in_polygon(39.9300, 32.8650, KARE))
        self.assertFalse(point_in_polygon(39.9230, 32.8800, KARE))

    def test_icbukey_alanin_girintisi_disaridadir(self):
        # L_ALAN'da saf ust-sag koseyi kesen girinti
        self.assertFalse(point_in_polygon(39.9250, 32.8680, L_ALAN))
        self.assertTrue(point_in_polygon(39.9210, 32.8680, L_ALAN))


class SurveyGridTest(unittest.TestCase):
    def test_rota_poligon_disina_tasmaz(self):
        """Kritik: uretilen hicbir nokta alanin disinda olmamali."""
        rota = survey_grid(KARE, spacing_m=100, margin_m=2)
        for lat, lon in rota:
            self.assertTrue(
                point_in_polygon(lat, lon, KARE),
                f"nokta alan disinda: {lat}, {lon}",
            )

    def test_pay_verilmeden_de_sinirlari_asmaz(self):
        """margin_m=0'da noktalar SINIRDA olabilir ama disari TASMAMALI."""
        (lat0, lon0), (x_min, x_max, y_min, y_max) = yerel_kutu(KARE)
        for lat, lon in survey_grid(KARE, spacing_m=100):
            x, y = to_local(lat, lon, lat0, lon0)
            self.assertLessEqual(x, x_max + 1e-6)
            self.assertGreaterEqual(x, x_min - 1e-6)
            self.assertLessEqual(y, y_max + 1e-6)
            self.assertGreaterEqual(y, y_min - 1e-6)

    def test_hat_araligi_istenen_degere_esit(self):
        aralik = 120.0
        rota = survey_grid(KARE, spacing_m=aralik)
        (lat0, lon0), _ = yerel_kutu(KARE)
        # Her hat iki noktadan olusur; hatlarin y degerleri aralik kadar artmali.
        y_degerleri = []
        for i in range(0, len(rota), 2):
            _, y = to_local(rota[i][0], rota[i][1], lat0, lon0)
            y_degerleri.append(y)
        farklar = [b - a for a, b in zip(y_degerleri, y_degerleri[1:])]
        self.assertTrue(farklar, "tek hat uretildi, aralik olculemedi")
        for fark in farklar:
            self.assertAlmostEqual(fark, aralik, delta=0.5)

    def test_gidis_donus_deseni(self):
        """Ardisik hatlar TERS yonde gezilmeli — ucun hat sonunda bosa
        donmemesi icin (boustrophedon)."""
        rota = survey_grid(KARE, spacing_m=100)
        (lat0, lon0), _ = yerel_kutu(KARE)
        yonler = []
        for i in range(0, len(rota) - 1, 2):
            x1, _ = to_local(rota[i][0], rota[i][1], lat0, lon0)
            x2, _ = to_local(rota[i + 1][0], rota[i + 1][1], lat0, lon0)
            yonler.append(1 if x2 > x1 else -1)
        for onceki, sonraki in zip(yonler, yonler[1:]):
            self.assertNotEqual(onceki, sonraki, "hatlar ayni yonde geziliyor")

    def test_daha_dar_aralik_daha_uzun_rota(self):
        kisa = route_length_m(survey_grid(KARE, spacing_m=200))
        uzun = route_length_m(survey_grid(KARE, spacing_m=100))
        self.assertGreater(uzun, kisa)

    def test_aci_hatlarin_yonunu_degistirir(self):
        yatay = survey_grid(KARE, spacing_m=150, angle_deg=0)
        dikey = survey_grid(KARE, spacing_m=150, angle_deg=90)
        self.assertNotEqual(
            [(round(a, 6), round(b, 6)) for a, b in yatay],
            [(round(a, 6), round(b, 6)) for a, b in dikey],
        )
        # 90 derecede hatlar kuzey-guney uzanir: bir hattin iki ucu ayni
        # boylamda, farkli enlemde olmali.
        self.assertAlmostEqual(dikey[0][1], dikey[1][1], places=4)
        self.assertNotAlmostEqual(dikey[0][0], dikey[1][0], places=4)

    def test_icbukey_alanda_girinti_atlanir(self):
        rota = survey_grid(L_ALAN, spacing_m=80, margin_m=2)
        for lat, lon in rota:
            self.assertTrue(
                point_in_polygon(lat, lon, L_ALAN),
                f"icbukey alanin girintisine nokta konuldu: {lat}, {lon}",
            )

    def test_gecersiz_girdiler(self):
        with self.assertRaises(ValueError):
            survey_grid([(39.92, 32.86), (39.93, 32.87)], spacing_m=100)
        with self.assertRaises(ValueError):
            survey_grid(KARE, spacing_m=0)
        with self.assertRaises(ValueError):
            survey_grid(KARE, spacing_m=-50)

    def test_alandan_buyuk_aralik_tek_hat_uretir(self):
        """Hat araligi alandan buyukse bu hata DEGILDIR: genis bir tarama
        seridi tek gecisle kapanir, ortadan tek hat uretilir."""
        rota = survey_grid(KARE, spacing_m=100000)
        self.assertEqual(len(rota), 2, "tek hat (iki uc nokta) bekleniyordu")

    def test_pay_alani_tamamen_yerse_anlasilir_hata_verir(self):
        with self.assertRaises(ValueError) as tutamac:
            survey_grid(KARE, spacing_m=50, margin_m=5000)
        mesaj = str(tutamac.exception).lower()
        self.assertIn("sigmiyor", mesaj)
        self.assertIn("kenar payi", mesaj)


class ExpandingSquareTest(unittest.TestCase):
    MERKEZ = (39.925, 32.866)

    def test_nokta_sayisi_bacak_sayisinin_bir_fazlasi(self):
        self.assertEqual(len(expanding_square(self.MERKEZ, 50, legs=8)), 9)

    def test_merkezden_baslar(self):
        rota = expanding_square(self.MERKEZ, 50, legs=4)
        self.assertAlmostEqual(rota[0][0], self.MERKEZ[0], places=9)
        self.assertAlmostEqual(rota[0][1], self.MERKEZ[1], places=9)

    def test_bacak_uzunluklari_d_d_2d_2d_sirasini_izler(self):
        d = 60.0
        rota = expanding_square(self.MERKEZ, d, legs=6)
        lat0, lon0 = self.MERKEZ
        yerel = [to_local(p[0], p[1], lat0, lon0) for p in rota]
        uzunluklar = [
            math.hypot(yerel[i + 1][0] - yerel[i][0], yerel[i + 1][1] - yerel[i][1])
            for i in range(len(yerel) - 1)
        ]
        for beklenen, gelen in zip([d, d, 2 * d, 2 * d, 3 * d, 3 * d], uzunluklar):
            self.assertAlmostEqual(gelen, beklenen, delta=0.5)

    def test_her_bacakta_90_derece_donulur(self):
        rota = expanding_square(self.MERKEZ, 50, legs=5)
        lat0, lon0 = self.MERKEZ
        yerel = [to_local(p[0], p[1], lat0, lon0) for p in rota]
        yonler = [
            math.atan2(yerel[i + 1][0] - yerel[i][0], yerel[i + 1][1] - yerel[i][1])
            for i in range(len(yerel) - 1)
        ]
        for onceki, sonraki in zip(yonler, yonler[1:]):
            fark = (sonraki - onceki) % (2 * math.pi)
            self.assertAlmostEqual(fark, math.pi / 2, delta=0.01)

    def test_ilk_bacak_verilen_yone_gider(self):
        """start_heading 0 = kuzey."""
        rota = expanding_square(self.MERKEZ, 100, legs=1, start_heading_deg=0)
        x, y = to_local(rota[1][0], rota[1][1], *self.MERKEZ)
        self.assertAlmostEqual(x, 0.0, delta=0.5)
        self.assertAlmostEqual(y, 100.0, delta=0.5)

    def test_desen_disa_dogru_genisler(self):
        rota = expanding_square(self.MERKEZ, 50, legs=10)
        lat0, lon0 = self.MERKEZ
        uzakliklar = [
            math.hypot(*to_local(p[0], p[1], lat0, lon0)) for p in rota
        ]
        self.assertGreater(uzakliklar[-1], uzakliklar[2])

    def test_gecersiz_girdiler(self):
        with self.assertRaises(ValueError):
            expanding_square(self.MERKEZ, 0, legs=4)
        with self.assertRaises(ValueError):
            expanding_square(self.MERKEZ, 50, legs=0)


class RotaUzunluguTest(unittest.TestCase):
    def test_tek_nokta_sifir(self):
        self.assertEqual(route_length_m([(39.9, 32.8)]), 0.0)

    def test_bilinen_mesafe(self):
        """0.01 derece enlem farki ~ 1111 m."""
        uzunluk = route_length_m([(39.9200, 32.8600), (39.9300, 32.8600)])
        self.assertAlmostEqual(uzunluk, 1111.9, delta=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
