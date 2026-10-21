"""Three planes, the house layout for every screen:
big type in the back, the subject in the middle, the one signal button on top.
The overlap is what gives the screen depth, so the subject card sits over the bottom of the big type
and the button sits over the bottom edge of the card."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton, QWidget

from .theme import BACK_TYPE, INK, INK_SOFT, LINE_RGBA, PANEL, SAND, SAND_2


class Stage(QWidget):
    def __init__(self, subject: QWidget, button: QPushButton, back="", huge=96, align_button="center"):
        super().__init__()
        self.subject, self.button, self.back, self.huge = subject, button, back, huge
        self.align_button = align_button
        subject.setParent(self)
        button.setParent(self)
        self.card = QRectF()

    def set_back(self, text):
        self.back = text
        self._place()
        self.update()

    def _font(self):
        f = QFont("Space Grotesk")
        f.setPixelSize(self.huge)
        f.setWeight(QFont.Bold)
        f.setLetterSpacing(QFont.PercentageSpacing, 96)
        return f

    def _place(self):
        w, h = self.width(), self.height()
        bh, bw = 44, max(self.button.sizeHint().width(), 150)     # 44 tall so the 22px radius makes a pill
        top = int(self.huge * 0.62)                                  # card covers the lower part of the big type
        self.card = QRectF(10, top, w - 20, h - top - bh / 2 - 6)
        pad, foot = 8, bh / 2 + 6                                    # the button never covers the subject itself
        self.subject.setGeometry(self.card.adjusted(pad, pad, -pad, -foot).toRect())
        x = {"center": (w - bw) / 2, "right": self.card.right() - bw - 18}[self.align_button]
        self.button.setGeometry(int(x), int(self.card.bottom() - bh / 2), int(bw), bh)
        self.button.raise_()

    def resizeEvent(self, e):
        self._place()

    def showEvent(self, e):
        self._place()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # back plane: the one huge thing, tone on tone
        if self.back:
            p.setFont(self._font())
            p.setPen(QColor(BACK_TYPE))
            fm = QFontMetrics(p.font())
            text = fm.elidedText(self.back, Qt.ElideRight, self.width() - 4)
            p.drawText(QPointF(2, fm.ascent() * 0.86), text)
        # middle plane: a raised card with a soft teal shadow
        p.setPen(Qt.NoPen)
        for i in range(1, 15):                       # soft, wide falloff instead of hard bands
            p.setBrush(QColor(14, 58, 64, 3))
            p.drawRoundedRect(self.card.adjusted(-i / 2 + 6, i * 0.8, i / 2 - 6, i * 1.1), 18 + i / 2, 18 + i / 2)
        p.setBrush(QColor(PANEL))
        p.setPen(QPen(QColor(*LINE_RGBA), 1))
        p.drawRoundedRect(self.card, 18, 18)


class Preview(QWidget):
    """What the video will look like: the screen with the bubble in its shape, or just the camera."""

    def __init__(self, bubble):
        super().__init__()
        self.bubble = bubble
        self.mode = "both"
        self.cam = None
        self.shot = None
        self.target = None         # QRect of a window or area, None for the whole screen
        bubble.frame_ready.connect(self._cam)
        self.grab_timer = QTimer(self, interval=1500, timeout=self._grab)

    def set_mode(self, mode):
        self.mode = mode
        if mode == "cam":
            self.grab_timer.stop()
            self.shot = None
        else:
            self._grab()
            self.grab_timer.start()
        self.update()

    def set_target(self, rect):
        self.target = rect
        self.update()

    def _cam(self, img: QImage):
        self.cam = img
        if self.isVisible():
            self.update()

    def _grab(self):
        if not self.isVisible():
            return
        s = QGuiApplication.primaryScreen()
        pm = s.grabWindow(0)
        if not pm.isNull():
            self.shot = pm.toImage().scaledToWidth(720, Qt.SmoothTransformation)
            self.update()

    def showEvent(self, e):
        if self.mode != "cam":
            self._grab()
            self.grab_timer.start()

    def hideEvent(self, e):
        self.grab_timer.stop()

    @staticmethod
    def _cover(p, img, r, mirror=False):
        if img is None or img.isNull():
            return
        if mirror:
            img = img.mirrored(True, False)
        k = max(r.width() / img.width(), r.height() / img.height())
        w, h = r.width() / k, r.height() / k
        p.drawImage(r, img, QRectF((img.width() - w) / 2, (img.height() - h) / 2, w, h))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 12, 12)
        p.setClipPath(clip)
        p.fillRect(r, QColor(INK))
        if self.mode == "cam":
            self._cover(p, self.cam, r, mirror=True)
            return
        scr = QGuiApplication.primaryScreen().geometry()
        area = QRectF(self.target) if self.target is not None else QRectF(scr)
        if self.shot is not None and not self.shot.isNull():
            ks = self.shot.width() / max(scr.width(), 1)
            src = QRectF((area.x() - scr.x()) * ks, (area.y() - scr.y()) * ks, area.width() * ks, area.height() * ks)
            k = max(r.width() / src.width(), r.height() / src.height())
            w, h = r.width() / k, r.height() / k
            p.drawImage(r, self.shot, QRectF(src.center().x() - w / 2, src.center().y() - h / 2, w, h))
        else:
            p.fillRect(r, QColor(SAND_2))
            p.setPen(QColor(INK_SOFT))
            label = "Your screen" if self.target is None else f"{self.target.width()} × {self.target.height()}"
            p.drawText(r.adjusted(14, 10, -14, -10), Qt.AlignTop | Qt.AlignRight, label)
        if self.mode != "both":
            return
        # the bubble, scaled like it will appear in the recording
        bw, bh = self.bubble._dims()
        k = r.width() / max(area.width(), 1)
        b = QRectF(r.left() + 40 * k, r.bottom() - (bh + 40) * k, bw * k, bh * k)
        path = QPainterPath()
        if self.bubble.shape == "round":
            path.addEllipse(b)
        else:
            rad = min(b.width(), b.height()) * (0.16 if self.bubble.shape == "square" else 0.1)
            path.addRoundedRect(b, rad, rad)
        p.save()
        p.setClipPath(path)
        p.fillPath(path, QColor(INK))
        self._cover(p, self.cam, b, mirror=True)
        p.restore()
        p.setPen(QPen(QColor(SAND), 2))
        p.drawPath(path)
