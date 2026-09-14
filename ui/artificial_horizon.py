"""
artificial_horizon.py
-----------------------
Klasik kokpit tarzi Yapay Ufuk (Artificial Horizon / Attitude Indicator) gostergesi.
Pitch ve Roll degerlerine gore gokyuzu/yer yarim daireleri doner ve kayar.
Gercekci gorunum icin gradyan renkler, derece isaretleri ve metalik cerceve icerir.
"""

import math
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QPolygonF, QLinearGradient, QRadialGradient, QFont
)
from PyQt5.QtCore import Qt, QPointF, QRectF


class ArtificialHorizon(QWidget):
    def __init__(self):
        super().__init__()
        self.pitch_deg = 0.0
        self.roll_deg = 0.0
        self.setMinimumSize(220, 220)

    def set_attitude(self, pitch_rad: float, roll_rad: float):
        self.pitch_deg = math.degrees(pitch_rad)
        self.roll_deg = math.degrees(roll_rad)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = min(self.width(), self.height())
        cx = self.width() / 2
        cy = self.height() / 2
        radius = size / 2 - 14

        # --- Dis metalik cerceve ---
        bezel_gradient = QRadialGradient(cx, cy, radius + 14)
        bezel_gradient.setColorAt(0.0, QColor("#4a4a55"))
        bezel_gradient.setColorAt(0.85, QColor("#2a2a33"))
        bezel_gradient.setColorAt(1.0, QColor("#111116"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bezel_gradient))
        painter.drawEllipse(QPointF(cx, cy), radius + 14, radius + 14)

        # --- Ic gosterge alani (donen kisim) ---
        painter.save()
        painter.setClipRect(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        painter.translate(cx, cy)
        painter.rotate(-self.roll_deg)

        pitch_offset = max(-radius * 1.8, min(radius * 1.8, self.pitch_deg * (radius / 30.0)))
        big = radius * 3.5

        # Gokyuzu gradyani
        sky_gradient = QLinearGradient(0, -big + pitch_offset, 0, pitch_offset)
        sky_gradient.setColorAt(0.0, QColor("#1a5fb4"))
        sky_gradient.setColorAt(1.0, QColor("#62a0e8"))
        painter.setBrush(QBrush(sky_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(-big, -big + pitch_offset, big * 2, big))

        # Yer gradyani
        ground_gradient = QLinearGradient(0, pitch_offset, 0, big + pitch_offset)
        ground_gradient.setColorAt(0.0, QColor("#8a6238"))
        ground_gradient.setColorAt(1.0, QColor("#4a3018"))
        painter.setBrush(QBrush(ground_gradient))
        painter.drawRect(QRectF(-big, pitch_offset, big * 2, big))

        # Ufuk cizgisi
        painter.setPen(QPen(QColor("#ffffff"), 2.5))
        painter.drawLine(QPointF(-big, pitch_offset), QPointF(big, pitch_offset))

        # Pitch merdiveni (derece cizgileri + rakamlar)
        font = QFont("Sans", 8, QFont.Bold)
        painter.setFont(font)
        for deg in range(-90, 91, 10):
            if deg == 0:
                continue
            y = pitch_offset - deg * (radius / 30.0)
            if abs(y) > radius:
                continue
            is_major = (deg % 20 == 0)
            half_w = 26 if is_major else 14
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.drawLine(QPointF(-half_w, y), QPointF(half_w, y))
            if is_major:
                painter.setPen(QColor("#ffffff"))
                painter.drawText(QRectF(half_w + 2, y - 8, 30, 16), Qt.AlignVCenter, str(abs(deg)))
                painter.drawText(QRectF(-half_w - 32, y - 8, 30, 16), Qt.AlignVCenter | Qt.AlignRight, str(abs(deg)))

        painter.restore()

        # --- Sabit roll skalasi (ust yay + ucgen isaretciler) ---
        painter.setPen(QPen(QColor("#f0f0f0"), 2))
        for angle in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle)
            outer = radius + 2
            inner = radius - (10 if angle in (0, -30, 30, -60, 60) else 5)
            painter.drawLine(QPointF(0, -outer), QPointF(0, -inner))
            painter.restore()

        # Roll pozisyon ucgeni (donen)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.roll_deg)
        triangle = QPolygonF([
            QPointF(0, -radius + 4),
            QPointF(-7, -radius + 16),
            QPointF(7, -radius + 16),
        ])
        painter.setBrush(QBrush(QColor("#f9e2af")))
        painter.setPen(QPen(QColor("#1e1e2e"), 1))
        painter.drawPolygon(triangle)
        painter.restore()

        # Sabit ust ucgen (referans, 0 derece)
        fixed_triangle = QPolygonF([
            QPointF(cx, cy - radius - 2),
            QPointF(cx - 7, cy - radius - 14),
            QPointF(cx + 7, cy - radius - 14),
        ])
        painter.setBrush(QBrush(QColor("#e0e0e0")))
        painter.setPen(QPen(QColor("#1e1e2e"), 1))
        painter.drawPolygon(fixed_triangle)

        # --- Merkez ucak sembolu (sabit) ---
        painter.setPen(QPen(QColor("#1e1e2e"), 4.5))
        painter.drawLine(QPointF(cx - 42, cy), QPointF(cx - 12, cy))
        painter.drawLine(QPointF(cx + 12, cy), QPointF(cx + 42, cy))
        painter.drawLine(QPointF(cx - 12, cy), QPointF(cx, cy + 10))
        painter.drawLine(QPointF(cx + 12, cy), QPointF(cx, cy + 10))

        painter.setPen(QPen(QColor("#f9e2af"), 2.5))
        painter.drawLine(QPointF(cx - 40, cy), QPointF(cx - 12, cy))
        painter.drawLine(QPointF(cx + 12, cy), QPointF(cx + 40, cy))
        painter.drawLine(QPointF(cx - 12, cy), QPointF(cx, cy + 9))
        painter.drawLine(QPointF(cx + 12, cy), QPointF(cx, cy + 9))

        painter.setBrush(QBrush(QColor("#f9e2af")))
        painter.setPen(QPen(QColor("#1e1e2e"), 1))
        painter.drawEllipse(QPointF(cx, cy), 3.5, 3.5)

        # --- Cerceve dis cizgisi (parlaklik hissi) ---
        painter.setPen(QPen(QColor("#6b6b78"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
