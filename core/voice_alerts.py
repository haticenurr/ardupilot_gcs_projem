"""
voice_alerts.py
----------------
Kritik durumlarda sesli uyari (TTS).

Pilot ekrana bakmadigi anlarda dusuk pil / geofence ihlali / baglanti
kaybi gibi uyarilarin kacirilmamasi icin isletim sistemine gomulu metin
okuma araclari kullanilir — ek Python bagimliligi GEREKMEZ:

    macOS    : say
    Linux    : spd-say, yoksa espeak-ng / espeak
    Windows  : PowerShell (System.Speech.Synthesis)

Tasarim kurallari:
  - Konusma AYRI bir thread'de, kuyruk uzerinden yapilir. GUI hicbir
    kosulda beklemez.
  - Ayni uyari, bekleme suresi (`min_interval_s`) dolmadan tekrarlanmaz;
    aksi halde dusuk pil uyarisi saniyede birkac kez tekrarlanirdi.
  - TTS bulunmayan sistemde uygulama sessizce calismaya devam eder.
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import time

# Kuyruk bu uzunlugu asarsa yeni istekler dusurulur: uyarilar birikip
# dakikalarca geriden konusmaya baslamasin.
MAX_KUYRUK = 8

# Tek bir anonsun tamamlanmasi icin verilen ust sinir (saniye).
KONUSMA_ZAMAN_ASIMI = 15


def _komut_var(ad):
    return shutil.which(ad) is not None


def _macos_turkce_ses():
    """macOS'ta yuklu bir Turkce ses varsa adini doner (orn. 'Yelda').
    Bulunamazsa None — o zaman sistem varsayilan sesi kullanilir."""
    try:
        cikti = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return None
    for satir in cikti.splitlines():
        # Satir bicimi: "Yelda              tr_TR    # Merhaba! ..."
        if "tr_TR" in satir:
            return satir.split()[0]
    return None


def detect_backend():
    """Bu isletim sisteminde calisan bir konusma fonksiyonu dondurur.
    Hicbiri yoksa None doner (ses ozelligi sessizce devre disi kalir)."""
    if sys.platform == "darwin" and _komut_var("say"):
        ses = _macos_turkce_ses()

        def _mac(text):
            komut = ["say"]
            if ses:
                komut += ["-v", ses]
            komut.append(text)
            subprocess.run(komut, timeout=KONUSMA_ZAMAN_ASIMI)

        return _mac

    if sys.platform.startswith("win"):
        def _win(text):
            # Metni PowerShell'e tirnak kacisiyla guvenli sekilde gecir.
            guvenli = text.replace("'", "''")
            betik = (
                "Add-Type -AssemblyName System.Speech; "
                "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                f".Speak('{guvenli}')"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", betik],
                timeout=KONUSMA_ZAMAN_ASIMI,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        return _win

    if _komut_var("spd-say"):
        def _spd(text):
            subprocess.run(
                ["spd-say", "-l", "tr", "-w", text], timeout=KONUSMA_ZAMAN_ASIMI
            )
        return _spd

    for ad in ("espeak-ng", "espeak"):
        if _komut_var(ad):
            def _espeak(text, _ad=ad):
                subprocess.run([_ad, "-v", "tr", text], timeout=KONUSMA_ZAMAN_ASIMI)
            return _espeak

    return None


class VoiceAlerts:
    """Kuyruk + tek thread uzerinden sesli uyari yoneticisi."""

    def __init__(self, enabled=True, backend=None):
        # backend testlerde sahte bir fonksiyonla degistirilebilir.
        self._backend = backend if backend is not None else detect_backend()
        self._enabled = bool(enabled) and self._backend is not None
        self._queue = queue.Queue()
        self._son_soylenen = {}
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._dusurulen = 0

    # ---------------- durum ----------------

    @property
    def available(self):
        """Sistemde calisan bir TTS araci var mi?"""
        return self._backend is not None

    @property
    def enabled(self):
        return self._enabled

    def set_enabled(self, enabled: bool):
        """Sesi acar/kapatir. Kapatildiginda bekleyen kuyruk bosaltilir;
        kapali durumda hicbir alt surec baslatilmaz."""
        enabled = bool(enabled) and self.available
        self._enabled = enabled
        if not enabled:
            self._kuyrugu_bosalt()
        return enabled

    # ---------------- konusma ----------------

    def say(self, text, key=None, min_interval_s=10.0):
        """Bir anonsu kuyruga alir.

        key: throttle kimligi (verilmezse metnin kendisi). Ayni key
             `min_interval_s` dolmadan tekrar seslendirilmez.
        """
        if not self._enabled or not text:
            return False
        anahtar = key or text
        simdi = time.time()
        with self._lock:
            son = self._son_soylenen.get(anahtar)
            if son is not None and (simdi - son) < min_interval_s:
                return False
            self._son_soylenen[anahtar] = simdi

        if self._queue.qsize() >= MAX_KUYRUK:
            self._dusurulen += 1
            return False

        self._basla()
        self._queue.put(text)
        return True

    def _basla(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._dongu, name="VoiceAlerts", daemon=True
        )
        self._thread.start()

    def _dongu(self):
        while self._running:
            try:
                text = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            if text is None:
                break
            if not self._enabled:
                continue
            try:
                self._backend(text)
            except Exception as e:
                # Ses hicbir zaman ucusu etkilememeli: hata yalnizca
                # raporlanir, uygulama calismaya devam eder.
                print(f"[VoiceAlerts] Seslendirme hatasi: {e}")

    def _kuyrugu_bosalt(self):
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def stop(self):
        """Uygulama kapanirken cagrilir."""
        self._running = False
        self._kuyrugu_bosalt()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    # ---------------- test yardimcisi ----------------

    def wait_idle(self, timeout=5.0):
        """Kuyruktaki tum anonslar seslendirilene kadar bekler."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._queue.empty():
                time.sleep(0.05)
                if self._queue.empty():
                    return True
            time.sleep(0.02)
        return self._queue.empty()
