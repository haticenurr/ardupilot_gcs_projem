"""
mavlink_env.py
---------------
pymavlink'i MAVLink 2 diyalektiyle calistirir.

NEDEN GEREKLI
-------------
pymavlink, `MAVLINK20` ortam degiskeni AYARLANMAMISSA varsayilan olarak
`pymavlink.dialects.v10.*` (MAVLink 1) modulunu yukler. MAVLink 1
tanimlarinda gorev mesajlarinin `mission_type` alani YOKTUR ve
fonksiyon imzalarinda son parametre `force_mavlink1`'dir:

    v1:  mission_clear_all_send(hedef_sistem, hedef_bilesen, force_mavlink1)
    v2:  mission_clear_all_send(hedef_sistem, hedef_bilesen, mission_type,
                                force_mavlink1)

Bu yuzden `mission_clear_all_send(..., MAV_MISSION_TYPE_FENCE)` gibi bir
cagri, MAVLink 1 altinda fence tipini sessizce `force_mavlink1`
parametresine gecirir. Sonuc: poligon geofence ve rally noktalari, kendi
tablolari yerine VARSAYILAN GOREV TABLOSUNA yazilir — yani fence
yuklemek ucus gorevini silebilir.

Bu modul, pymavlink ilk kez import edilmeden ONCE yuklenmelidir; bu
yuzden `core/drone_telemetry.py` ve testlerdeki sahte arac, pymavlink
importundan once burayi import eder.

ArduPilot 4.x zaten MAVLink 2 konusur, dolayisiyla v2'ye gecmenin bir
uyumluluk maliyeti yoktur.
"""

import os

os.environ.setdefault("MAVLINK20", "1")

# Ortam degiskenini ayarlamak, pymavlink HENUZ import edilmediyse yeterlidir.
# Ancak baska bir modul (orn. bir test dosyasi) pymavlink'i daha once import
# etmis olabilir; o durumda diyalekt zaten v1 olarak sys.modules'a girmistir
# ve ortam degiskeni bir ise yaramaz. Bu yuzden diyalekti acikca kontrol edip
# gerekirse yeniden yukluyoruz — boylece duzeltme IMPORT SIRASINDAN bagimsiz
# calisir.
try:
    from pymavlink import mavutil as _mavutil

    if "v20" not in _mavutil.mavlink.__name__:
        _mavutil.set_dialect(os.environ.get("MAVLINK_DIALECT", "ardupilotmega"))
except Exception as _hata:  # pragma: no cover - pymavlink yoksa sessiz gec
    print(f"[mavlink_env] MAVLink 2 diyalekti secilemedi: {_hata}")


def mavlink2_aktif():
    """Tani amacli: yuklu diyalektin MAVLink 2 olup olmadigini soyler."""
    from pymavlink import mavutil

    return "v20" in mavutil.mavlink.__name__
