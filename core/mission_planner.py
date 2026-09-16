"""
mission_planner.py
-------------------
Otomatik rota uretimi: `survey_grid` (alan tarama, Haritalama modu) ve
`expanding_square` (arama deseni, Arama Kurtarma modu).

Saf fonksiyonlardir; Qt ve MAVLink bilmez, dogrudan test edilir.

Hesaplar bolge merkezine oturtulmus yerel duzlemde (x = dogu, y = kuzey,
metre) yapilir; kucuk alanlarda esdikdortgen izdusum yeterince dogrudur.
"""

import math

R_DUNYA = 6371000.0  # metre


# --------------------------------------------------------------------------
# Izdusum
# --------------------------------------------------------------------------


def to_local(lat, lon, lat0, lon0):
    """WGS84 -> yerel duzlem (metre). x dogu, y kuzey."""
    x = math.radians(lon - lon0) * R_DUNYA * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R_DUNYA
    return x, y


def to_latlon(x, y, lat0, lon0):
    """Yerel duzlem (metre) -> WGS84."""
    lat = lat0 + math.degrees(y / R_DUNYA)
    lon = lon0 + math.degrees(x / (R_DUNYA * math.cos(math.radians(lat0))))
    return lat, lon


def haversine_m(lat1, lon1, lat2, lon2):
    """Iki WGS84 noktasi arasindaki buyuk daire mesafesi (metre).

    `a` hem alt hem ust sinirdan kirpilir: cok yakin noktalarda yuvarlama
    hatasi onu -1e-16 gibi negatif yapip sqrt'yi cokertiyordu."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = max(0.0, min(1.0, a))
    return 2 * R_DUNYA * math.asin(math.sqrt(a))


def centroid(points):
    """Nokta listesinin aritmetik ortalamasi (lat, lon)."""
    if not points:
        raise ValueError("Bos nokta listesi")
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _dondur(x, y, aci_rad):
    return (
        x * math.cos(aci_rad) - y * math.sin(aci_rad),
        x * math.sin(aci_rad) + y * math.cos(aci_rad),
    )


# --------------------------------------------------------------------------
# Kamera / hat araligi
# --------------------------------------------------------------------------


def spacing_from_camera(altitude_m, fov_deg, overlap=0.3):
    """Hat araligi = 2 * irtifa * tan(FOV/2) * (1 - ortusme)."""
    if altitude_m <= 0:
        raise ValueError("Irtifa sifirdan buyuk olmali")
    if not 0 < fov_deg < 180:
        raise ValueError("Gorus acisi 0-180 derece arasinda olmali")
    if not 0 <= overlap < 1:
        raise ValueError("Ortusme orani 0 ile 1 arasinda olmali (1 haric)")
    yer_genisligi = 2.0 * altitude_m * math.tan(math.radians(fov_deg) / 2.0)
    return yer_genisligi * (1.0 - overlap)


# --------------------------------------------------------------------------
# Poligon yardimcilari
# --------------------------------------------------------------------------


def point_in_polygon(lat, lon, polygon):
    """Isin (ray casting) yontemiyle nokta poligonun icinde mi?"""
    if not polygon or len(polygon) < 3:
        return False
    icinde = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i][0], polygon[i][1]
        lat_j, lon_j = polygon[j][0], polygon[j][1]
        if (lat_i > lat) != (lat_j > lat):
            kesisim_lon = lon_i + (lat - lat_i) * (lon_j - lon_i) / (lat_j - lat_i)
            if lon < kesisim_lon:
                icinde = not icinde
        j = i
    return icinde


def polygon_area_m2(polygon):
    """Poligonun yaklasik alani (metrekare). Ayakkabi baglama formulu."""
    if not polygon or len(polygon) < 3:
        return 0.0
    lat0, lon0 = centroid(polygon)
    yerel = [to_local(p[0], p[1], lat0, lon0) for p in polygon]
    toplam = 0.0
    n = len(yerel)
    for i in range(n):
        x1, y1 = yerel[i]
        x2, y2 = yerel[(i + 1) % n]
        toplam += x1 * y2 - x2 * y1
    return abs(toplam) / 2.0


def _yatay_kesisimler(yerel_poligon, y):
    """y yuksekligindeki yatay dogrunun poligonla kesisim x'leri (sirali)."""
    kesisimler = []
    n = len(yerel_poligon)
    for i in range(n):
        x1, y1 = yerel_poligon[i]
        x2, y2 = yerel_poligon[(i + 1) % n]
        if y1 == y2:
            continue  # yatay kenar: kesisim tanimsiz, atlanir
        # Yarim acik aralik: bir kose iki kez sayilmasin.
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            kesisimler.append(x1 + t * (x2 - x1))
    kesisimler.sort()
    return kesisimler


# --------------------------------------------------------------------------
# Haritalama: tarama rotasi
# --------------------------------------------------------------------------


def survey_grid(polygon, spacing_m, angle_deg=0.0, margin_m=0.0):
    """Poligonu tarayan gidis-donus rotasi; ardisik hatlar ters yonde
    gezilir. angle_deg: 0 = dogu-bati, 90 = kuzey-guney."""
    if not polygon or len(polygon) < 3:
        raise ValueError("Tarama alani icin en az 3 nokta gerekli")
    if spacing_m <= 0:
        raise ValueError("Hat araligi sifirdan buyuk olmali")

    lat0, lon0 = centroid(polygon)
    aci = math.radians(angle_deg)

    # Tarama hatlari YATAY olacak sekilde dondur.
    yerel = [to_local(p[0], p[1], lat0, lon0) for p in polygon]
    donuk = [_dondur(x, y, -aci) for x, y in yerel]

    y_degerleri = [p[1] for p in donuk]
    y_min, y_max = min(y_degerleri) + margin_m, max(y_degerleri) - margin_m
    if y_max <= y_min:
        # Alan paydan dar: tek orta hat.
        y_min = y_max = (min(y_degerleri) + max(y_degerleri)) / 2.0

    # Ilk hat yarim aralik iceride: kenar seridi de taranir.
    hatlar = []
    y = y_min + spacing_m / 2.0
    if y > y_max:
        y = (y_min + y_max) / 2.0
    while y <= y_max + 1e-9:
        kesisimler = _yatay_kesisimler(donuk, y)
        # Kesisimler ikiser ikiser poligon ICINDE kalan parcalari verir.
        for i in range(0, len(kesisimler) - 1, 2):
            x_bas, x_son = kesisimler[i], kesisimler[i + 1]
            if margin_m:
                x_bas += margin_m
                x_son -= margin_m
            if x_son > x_bas:
                hatlar.append((y, x_bas, x_son))
        y += spacing_m

    if not hatlar:
        # Kenar payi alani tamamen yemis veya poligon dejenere. Hat araliginin
        # alandan buyuk olmasi hata DEGILDIR; o durumda tek orta hat uretilir.
        raise ValueError(
            "Bu ayarlarla alana hic tarama hatti sigmiyor — "
            "kenar payini kucultun veya alani buyutun"
        )

    # Gidis-donus: her hat bir oncekinin ters yonunde gezilir.
    rota_yerel = []
    for indeks, (y_hat, x_bas, x_son) in enumerate(hatlar):
        if indeks % 2 == 0:
            uclar = [(x_bas, y_hat), (x_son, y_hat)]
        else:
            uclar = [(x_son, y_hat), (x_bas, y_hat)]
        rota_yerel.extend(uclar)

    # Dondurmeyi geri al ve cografi koordinata cevir.
    return [
        to_latlon(*_dondur(x, y, aci), lat0, lon0) for x, y in rota_yerel
    ]


# --------------------------------------------------------------------------
# Arama Kurtarma: genisleyen kare
# --------------------------------------------------------------------------


def expanding_square(center, spacing_m, legs=12, start_heading_deg=0.0):
    """Merkezden disa genisleyen kare arama deseni; bacaklar d, d, 2d, 2d,
    3d ... seklinde artar, her bacakta 90 derece donulur."""
    if spacing_m <= 0:
        raise ValueError("Hat araligi sifirdan buyuk olmali")
    if legs < 1:
        raise ValueError("En az 1 bacak gerekli")

    lat0, lon0 = center[0], center[1]
    x, y = 0.0, 0.0
    yerel = [(0.0, 0.0)]
    yon = math.radians(start_heading_deg)

    for i in range(legs):
        uzunluk = spacing_m * (i // 2 + 1)
        # Pusula yonu: 0 = kuzey (+y), saat yonunde artar.
        x += uzunluk * math.sin(yon)
        y += uzunluk * math.cos(yon)
        yerel.append((x, y))
        yon += math.pi / 2.0  # saat yonunde 90 derece

    return [to_latlon(px, py, lat0, lon0) for px, py in yerel]


# --------------------------------------------------------------------------
# Ortak
# --------------------------------------------------------------------------


def route_length_m(points):
    """Rotanin toplam uzunlugu (metre), yerel duzlemde hesaplanir."""
    if len(points) < 2:
        return 0.0
    lat0, lon0 = centroid(points)
    yerel = [to_local(p[0], p[1], lat0, lon0) for p in points]
    return sum(
        math.hypot(yerel[i + 1][0] - yerel[i][0], yerel[i + 1][1] - yerel[i][1])
        for i in range(len(yerel) - 1)
    )
