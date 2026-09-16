"""
exporters.py
-------------
Gorevleri ve ucus kayitlarini endustri standardi formatlara cevirir.

- `.waypoints` (QGC WPL 110): Mission Planner, QGroundControl ve diger
  GCS yazilimlarinin okudugu duz metin gorev formati.
- `.kml`: Google Earth'te rotanin 3 boyutlu goruntulenmesi.

Bu modul saf fonksiyonlardan olusur (dosya yazmaz, Qt bilmez); boylece
test edilmesi kolaydir ve arayuzden bagimsiz kullanilabilir.
"""

import csv
import os
from xml.sax.saxutils import escape

# QGC WPL 110 satir duzeni:
#   index  current  frame  command  p1 p2 p3 p4  x(lat)  y(lon)  z(alt)  autocontinue
WAYPOINTS_HEADER = "QGC WPL 110"

_MAV_FRAME_GLOBAL = 0              # mutlak irtifa (home satiri icin)
_MAV_FRAME_GLOBAL_RELATIVE_ALT = 3  # kalkis noktasina gore irtifa
_MAV_CMD_NAV_WAYPOINT = 16


def mission_to_waypoints(waypoints, home=None):
    """Gorevi QGC WPL 110 metnine cevirir; satir 0 HOME'dur ve yurutulmez,
    gercek waypointler 1'den baslar."""
    if not waypoints:
        raise ValueError("Disa aktarilacak waypoint yok")

    if home is None:
        home_lat, home_lon = waypoints[0][0], waypoints[0][1]
    else:
        home_lat, home_lon = home[0], home[1]

    satirlar = [WAYPOINTS_HEADER]
    satirlar.append(
        _wpl_satiri(
            index=0, current=1, frame=_MAV_FRAME_GLOBAL,
            lat=home_lat, lon=home_lon, alt=0.0,
        )
    )
    for i, (lat, lon, alt) in enumerate(waypoints, start=1):
        satirlar.append(
            _wpl_satiri(
                index=i, current=0, frame=_MAV_FRAME_GLOBAL_RELATIVE_ALT,
                lat=lat, lon=lon, alt=alt,
            )
        )
    return "\n".join(satirlar) + "\n"


def _wpl_satiri(index, current, frame, lat, lon, alt):
    alanlar = [
        str(index), str(current), str(frame), str(_MAV_CMD_NAV_WAYPOINT),
        "0", "0", "0", "0",
        f"{float(lat):.8f}", f"{float(lon):.8f}", f"{float(alt):.6f}",
        "1",  # autocontinue
    ]
    return "\t".join(alanlar)


def parse_waypoints(text):
    """QGC WPL 110 metnini [(lat, lon, alt), ...] listesine cevirir;
    home satiri (index 0) atlanir."""
    satirlar = [s for s in (text or "").splitlines() if s.strip()]
    if not satirlar or not satirlar[0].startswith("QGC WPL"):
        raise ValueError("Gecersiz .waypoints dosyasi (QGC WPL basligi yok)")
    sonuc = []
    for satir in satirlar[1:]:
        alanlar = satir.split("\t")
        if len(alanlar) < 12:
            continue
        index = int(alanlar[0])
        if index == 0:
            continue  # home slotu
        sonuc.append((float(alanlar[8]), float(alanlar[9]), float(alanlar[10])))
    return sonuc


# --------------------------------------------------------------------------
# KML
# --------------------------------------------------------------------------

_KML_SABLON = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{ad}</name>
    <Style id="rota">
      <LineStyle><color>{cizgi_rengi}</color><width>3</width></LineStyle>
      <PolyStyle><color>40ffaa50</color></PolyStyle>
    </Style>
{icerik}  </Document>
</kml>
"""


def _kml_koordinatlar(noktalar):
    """KML koordinat sirasi: BOYLAM,ENLEM,IRTIFA (lat/lon sirasi terstir)."""
    return " ".join(
        f"{float(lon):.8f},{float(lat):.8f},{float(alt):.2f}"
        for lat, lon, alt in noktalar
    )


def _kml_rota(noktalar, ad):
    return (
        "    <Placemark>\n"
        f"      <name>{escape(ad)}</name>\n"
        "      <styleUrl>#rota</styleUrl>\n"
        "      <LineString>\n"
        "        <extrude>1</extrude>\n"
        "        <tessellate>1</tessellate>\n"
        "        <altitudeMode>relativeToGround</altitudeMode>\n"
        f"        <coordinates>{_kml_koordinatlar(noktalar)}</coordinates>\n"
        "      </LineString>\n"
        "    </Placemark>\n"
    )


def _kml_isaret(lat, lon, alt, ad):
    return (
        "    <Placemark>\n"
        f"      <name>{escape(ad)}</name>\n"
        "      <Point>\n"
        "        <altitudeMode>relativeToGround</altitudeMode>\n"
        f"        <coordinates>{float(lon):.8f},{float(lat):.8f},{float(alt):.2f}</coordinates>\n"
        "      </Point>\n"
        "    </Placemark>\n"
    )


def mission_to_kml(waypoints, ad="Ucus Plani"):
    """Gorevi KML'e cevirir: rota cizgisi + her waypoint icin isaretci."""
    if not waypoints:
        raise ValueError("Disa aktarilacak waypoint yok")
    icerik = _kml_rota(waypoints, ad)
    for i, (lat, lon, alt) in enumerate(waypoints, start=1):
        icerik += _kml_isaret(lat, lon, alt, f"WP {i}")
    return _KML_SABLON.format(ad=escape(ad), cizgi_rengi="ff50aaff", icerik=icerik)


def flight_log_to_kml(csv_path, ad=None):
    """`logs/` altindaki bir ucus CSV kaydini KML'e cevirir.

    CSV basligi: timestamp, lat, lon, alt, groundspeed, heading, battery,
    mode, armed. Gecersiz/bos koordinat satirlari atlanir."""
    if ad is None:
        ad = os.path.splitext(os.path.basename(csv_path))[0]

    noktalar = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for satir in csv.DictReader(f):
            try:
                lat = float(satir["lat"])
                lon = float(satir["lon"])
                alt = float(satir["alt"])
            except (TypeError, ValueError, KeyError):
                continue
            # 0,0 gecerli bir konum degil; GPS kilidi oncesi satirlardir.
            if abs(lat) < 1e-9 and abs(lon) < 1e-9:
                continue
            noktalar.append((lat, lon, alt))

    if not noktalar:
        raise ValueError("Kayitta gecerli konum verisi yok")

    icerik = _kml_rota(noktalar, ad)
    icerik += _kml_isaret(*noktalar[0], "Kalkis")
    icerik += _kml_isaret(*noktalar[-1], "Inis")
    return _KML_SABLON.format(ad=escape(ad), cizgi_rengi="ff50ff50", icerik=icerik)
