import sys

print("1. Script basladi, Python surumu:", sys.version)
sys.stdout.flush()

try:
    from pymavlink import mavutil
    print("2. pymavlink import BASARILI")
except Exception as e:
    print("2. HATA - pymavlink import edilemedi:", repr(e))
    sys.exit(1)
sys.stdout.flush()

try:
    from core.drone_telemetry import DroneTelemetry
    print("3. core/drone_telemetry.py import BASARILI")
except Exception as e:
    print("3. HATA - core/drone_telemetry.py import edilemedi:", repr(e))
    sys.exit(1)
sys.stdout.flush()

print("4. Baglanti deneniyor (bu satirdan sonra DroneTelemetry sinifinin kendi print'i gormeliyiz)...")
sys.stdout.flush()

try:
    d = DroneTelemetry()
    print("5. BAGLANTI BASARILI!")
except Exception as e:
    print("5. HATA - baglanti kurulamadi:", repr(e))
    sys.exit(1)
sys.stdout.flush()

print("6. Tek bir veri paketi okunuyor...")
data = d.get_telemetry_data()
print("7. Gelen veri:", data)
