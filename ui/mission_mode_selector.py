"""
mission_mode_selector.py
-------------------------
Uc secenekli (Standart / Arama Kurtarma / Haritalama), animasyonlu gorev
modu seciciyi tanimlar. Aktif mod, ust kenarda kayan ince bir vurgu
cizgisiyle gosterilir (sekme gostergesi gibi) - boylece metnin ustune
binen bir kutu olmaz, okunabilirlik her zaman garanti olur.

Kullanim (main_v7.py icinde):
    self.mission_mode_selector = MissionModeSelector()
    self.mission_mode_selector.mode_changed.connect(self.on_mission_mode_changed)
    layout.addWidget(self.mission_mode_selector)
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFrame
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect


MODE_DEFS = [
    {"key": "Standart", "color": "#89dceb"},
    {"key": "Arama Kurtarma", "color": "#f38ba8"},
    {"key": "Haritalama", "color": "#f9e2af"},
]

INDICATOR_HEIGHT = 3


class MissionModeSelector(QWidget):
    mode_changed = pyqtSignal(str)  # secilen modun adini yayinlar

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_index = 0
        self.setFixedHeight(46)

        # Zemin (track): butonlarin en altinda, gorunmez sekilde durur.
        self._track = QFrame(self)
        self._track.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; border-radius: 10px;"
        )
        self._track.lower()

        # Butonlar: track'in ustunde, normal z-sirasinda olusturulur.
        self._buttons = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        for i, mode in enumerate(MODE_DEFS):
            btn = QPushButton(mode["key"])
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.setStyleSheet(self._button_style(active=False, color=mode["color"]))
            btn.clicked.connect(lambda _checked, idx=i: self.set_mode_index(idx, animate=True))
            row.addWidget(btn)
            self._buttons.append(btn)

        # Gosterge: en son olusturulup EN ONE alinir (raise_), ama sadece
        # ust kenarda INDICATOR_HEIGHT kadar ince bir serit oldugu icin
        # buton metniyle asla cakismaz.
        self._indicator = QFrame(self)
        self._indicator.setStyleSheet(
            f"background-color: {MODE_DEFS[0]['color']}; border-radius: 2px;"
        )
        self._indicator.raise_()

        self._apply_active_styles(animate=False)

    def _button_style(self, active: bool, color: str) -> str:
        text_color = color if active else "#a6adc8"
        return (
            "QPushButton {"
            "  background: transparent; border: none;"
            f"  color: {text_color}; font-weight: 700; font-size: 12px;"
            "  padding: 12px 14px 10px 14px;"
            "}"
            f"QPushButton:hover {{ color: {color if active else '#cdd6f4'}; }}"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._track.setGeometry(self.rect())
        self._position_indicator(self._current_index, animate=False)

    def _segment_rect(self, index: int) -> QRect:
        seg_w = self.width() / len(MODE_DEFS)
        pad = 14
        x = int(seg_w * index) + pad
        w = int(seg_w) - pad * 2
        return QRect(x, 0, max(w, 4), INDICATOR_HEIGHT)

    def _position_indicator(self, index: int, animate: bool):
        target = self._segment_rect(index)
        if animate:
            anim = QPropertyAnimation(self._indicator, b"geometry", self)
            anim.setDuration(260)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(self._indicator.geometry())
            anim.setEndValue(target)
            anim.start()
            self._anim = anim  # referansi sakla, cop toplayici silmesin
        else:
            self._indicator.setGeometry(target)

    def _apply_active_styles(self, animate: bool):
        color = MODE_DEFS[self._current_index]["color"]
        self._indicator.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        for i, btn in enumerate(self._buttons):
            mode = MODE_DEFS[i]
            btn.setStyleSheet(self._button_style(active=(i == self._current_index), color=mode["color"]))
        self._position_indicator(self._current_index, animate=animate)

    def set_mode_index(self, index: int, animate: bool = True):
        if index == self._current_index:
            return
        self._current_index = index
        self._apply_active_styles(animate=animate)
        self.mode_changed.emit(MODE_DEFS[index]["key"])

    def current_mode(self) -> str:
        return MODE_DEFS[self._current_index]["key"]
