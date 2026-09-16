"""
mavlink_env.py
---------------
pymavlink'i MAVLink 2 diyalektiyle calistirir.

MAVLINK20 ayarlanmazsa pymavlink MAVLink 1 yukler; orada gorev
mesajlarinin `mission_type` alani yoktur ve son parametre
`force_mavlink1`'dir:

    v1:  mission_clear_all_send(sistem, bilesen, force_mavlink1)
    v2:  mission_clear_all_send(sistem, bilesen, mission_type, force_mavlink1)

Kod v2 imzasina gore yazildigi icin, v1 altinda MAV_MISSION_TYPE_FENCE
degeri sessizce force_mavlink1'e gidiyor ve mission_type hic
gonderilmiyordu. ArduPilot 4.x zaten MAVLink 2 konusur.
"""

import os

os.environ.setdefault("MAVLINK20", "1")

# pymavlink daha once import edilmisse ortam degiskeni ise yaramaz; diyalekti
# kontrol edip gerekirse yeniden yukluyoruz (import sirasindan bagimsiz).
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
