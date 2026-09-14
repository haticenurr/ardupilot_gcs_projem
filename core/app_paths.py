"""
Uygulama dizinleri.

PyInstaller ile paketlenince kaynaklar sys.executable yaninda durur;
gelistirme ortaminda proje kokunu kullaniriz.
"""

import os
import sys


def application_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def logs_dir():
    path = os.path.join(application_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path
