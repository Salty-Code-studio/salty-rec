"""Visual window picker, like going live on Discord: a snapshot of every open window, click the one to record.

Three planes again: "Windows." huge at the back, the snapshot grid in the middle, and on the card you
point at a coral "Record this" pill on top of its edge. Coral shows on one card at a time, because only
that one is the tap."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import core, osui
from .theme import BACK_TYPE, INK, INK_MUTE, INK_SOFT, LINE, PANEL, SIGNAL, TEAL

CARD_W, CARD_H, THUMB_H = 260, 222, 150


class WindowCard(QWidget):
    clicked = Signal(dict)

    def __init__(self, win: dict):
        super().__init__()
        self.win = win
        self.hover = False
        self.img = QImage(win["thumb"]) if win.get("thumb") and Path(win["thumb"]).exists() else None
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{win['app']}\n{win['title']}")
        self.setFocusPolicy(Qt.StrongFocus)

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def focusInEvent(self, e):
        self.hover = True
        self.update()

    def focusOutEvent(self, e):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.win)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.win)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        card = QRectF(4, 4, CARD_W - 8, CARD_H - 24)
        # soft shadow, stronger when pointed at
        p.setPen(Qt.NoPen)
        for i in range(1, 9 if self.hover else 5):
            p.setBrush(QColor(14, 58, 64, 4))
            p.drawRoundedRect(card.adjusted(-i / 3 + 3, i * 0.7, i / 3 - 3, i), 14 + i / 2, 14 + i / 2)
        p.setBrush(QColor(PANEL))
        p.setPen(QPen(QColor(TEAL if self.hover else LINE), 1.5 if self.hover else 1))
        p.drawRoundedRect(card, 14, 14)
        # the snapshot, whole window visible
        shot = QRectF(card.left() + 8, card.top() + 8, card.width() - 16, THUMB_H - 8)
        clip = QPainterPath()
        clip.addRoundedRect(shot, 9, 9)
        p.save()
        p.setClipPath(clip)
        p.fillRect(shot, QColor("#EAE0CD"))
        if self.img is not None and not self.img.isNull():
            k = min(shot.width() / self.img.width(), shot.height() / self.img.height())
            w, h = self.img.width() * k, self.img.height() * k
            p.drawImage(QRectF(shot.center().x() - w / 2, shot.center().y() - h / 2, w, h), self.img)
        else:
            p.setPen(QColor(INK_MUTE))
            p.drawText(shot, Qt.AlignCenter, "No preview")
        p.restore()
        # names: app small and bold, title tiny
        f = QFont("Inter")
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(INK))
        tx = card.left() + 12
        p.drawText(QPointF(tx, card.top() + THUMB_H + 18),
                   QFontMetrics(f).elidedText(self.win["app"], Qt.ElideRight, int(card.width() - 24)))
        f2 = QFont("Inter")
        f2.setPixelSize(10)
        p.setFont(f2)
        p.setPen(QColor(INK_SOFT))
        p.drawText(QPointF(tx, card.top() + THUMB_H + 34),
                   QFontMetrics(f2).elidedText(self.win["title"], Qt.ElideRight, int(card.width() - 24)))
        # top plane: the one signal, only on the card you point at
        if self.hover:
            pill = QRectF(card.right() - 118, card.bottom() - 15, 106, 28)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(SIGNAL))
            p.drawRoundedRect(pill, 14, 14)
            f3 = QFont("Space Grotesk")
            f3.setPixelSize(12)
            f3.setWeight(QFont.Bold)
            p.setFont(f3)
            p.setPen(QColor("white"))
            p.drawText(pill, Qt.AlignCenter, "Record this")


class WindowPicker(QWidget):
    picked = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Pick a window")
        self.resize(900, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(6)
        top = QHBoxLayout()
        head = QLabel("Pick the window to record")
        head.setObjectName("brand")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        again = QPushButton("Refresh")
        again.setObjectName("text")
        again.setCursor(Qt.PointingHandCursor)
        again.clicked.connect(self.load)
        top.addWidget(head)
        top.addSpacing(8)
        top.addWidget(self.count)
        top.addStretch()
        top.addWidget(again)
        v.addLayout(top)
        v.addSpacing(64)                    # the grid starts over the lower part of the huge word
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(16)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        v.addWidget(self.scroll, 1)
        hint = QLabel("Picking a window brings it to the front when you start. Esc closes.")
        hint.setObjectName("muted")
        v.addWidget(hint)
        self.windows = []

    def open(self):
        self.show()
        osui.hide_from_capture(self)        # keep the picker out of its own snapshots
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(60, self.load)

    def load(self):
        self.count.setText("Looking…")
        self.setCursor(Qt.WaitCursor)
        self.windows = core.window_thumbs()
        self.unsetCursor()
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        cols = max(1, (self.scroll.viewport().width() + 14) // (CARD_W + 14))
        for i, win in enumerate(self.windows):
            card = WindowCard(win)
            card.clicked.connect(self._pick)
            self.grid.addWidget(card, i // cols, i % cols)
        n = len(self.windows)
        self.count.setText(f"{n} open" if n else "No windows found")

    def _pick(self, win):
        self.hide()
        self.picked.emit(win)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont("Space Grotesk")
        f.setPixelSize(120)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor(BACK_TYPE))
        p.drawText(QPointF(18, 52 + QFontMetrics(f).ascent() * 0.86), "Windows.")
