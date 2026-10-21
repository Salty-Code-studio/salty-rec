"""Floating windows: camera bubble, recording control bar, countdown."""
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from . import core, osui
from .theme import CORAL, INK, SAND

FLOAT = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool


class _Draggable(QWidget):
    def __init__(self):
        super().__init__(None, FLOAT)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self._drag = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class CameraBubble(_Draggable):
    """A real window on screen, so the screen recording captures it wherever you drag it."""
    SIZES = {"S": 170, "M": 240, "L": 340}
    SHAPES = {"round": "Round", "square": "Square", "wide": "Wide", "tall": "Tall"}
    shape_changed = Signal(str)
    size_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Drag to move. Double-click to change size. Right-click for shapes.")
        self.image = None
        self.size_key = "M"
        self.shape = "round"
        self.camera = None
        self.session = QMediaCaptureSession()
        self.sink = QVideoSink()
        self.sink.videoFrameChanged.connect(self._frame)
        self.session.setVideoSink(self.sink)
        self._apply_size()

    def set_camera(self, name: str | None):
        if self.camera:
            self.camera.stop()
            self.camera = None
        devices = QMediaDevices.videoInputs()
        dev = next((d for d in devices if d.description() == name), devices[0] if devices else None)
        if dev is None:
            return
        self.camera = QCamera(dev)
        self.session.setCamera(self.camera)
        if self.isVisible():
            self.camera.start()

    def set_size(self, key):
        self.size_key = key
        self._apply_size()

    def set_shape(self, shape):
        self.shape = shape if shape in self.SHAPES else "round"
        self._apply_size()

    def _dims(self):
        d = self.SIZES[self.size_key]
        if self.shape == "wide":
            return round(d * 16 / 9), d
        if self.shape == "tall":
            return round(d * 3 / 4), d
        return d, d

    def _apply_size(self):
        c = self.geometry().center()
        w, h = self._dims()
        self.resize(w, h)
        if self.isVisible():
            self.move(c - QPoint(w // 2, h // 2))
        self.update()

    def place_default(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        d = self.width()
        self.move(g.left() + 40, g.bottom() - d - 40)

    def showEvent(self, e):
        super().showEvent(e)
        osui.float_everywhere(self)
        if self.camera:
            self.camera.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        if self.camera:
            self.camera.stop()
        self.image = None

    def mouseDoubleClickEvent(self, e):
        order = list(self.SIZES)
        self.set_size(order[(order.index(self.size_key) + 1) % len(order)])
        self.size_changed.emit(self.size_key)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        for key, name in self.SHAPES.items():
            a = m.addAction(name, lambda k=key: (self.set_shape(k), self.shape_changed.emit(k)))
            a.setCheckable(True)
            a.setChecked(key == self.shape)
        m.addSeparator()
        for key, name in (("S", "Small"), ("M", "Medium"), ("L", "Large")):
            a = m.addAction(name, lambda k=key: (self.set_size(k), self.size_changed.emit(k)))
            a.setCheckable(True)
            a.setChecked(key == self.size_key)
        m.exec(e.globalPos())

    def _path(self, r):
        path = QPainterPath()
        if self.shape == "round":
            path.addEllipse(r)
        else:
            radius = min(r.width(), r.height()) * (0.16 if self.shape == "square" else 0.1)
            path.addRoundedRect(r, radius, radius)
        return path

    def _frame(self, frame):
        self.image = frame.toImage()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        path = self._path(r)
        p.setClipPath(path)
        p.fillPath(path, QColor(INK))
        if self.image is not None and not self.image.isNull():
            img = self.image.mirrored(True, False)
            k = max(r.width() / img.width(), r.height() / img.height())
            w, h = r.width() / k, r.height() / k
            src = QRectF((img.width() - w) / 2, (img.height() - h) / 2, w, h)
            p.drawImage(r, img, src)
        p.setClipping(False)
        if self.image is None:
            p.setPen(QColor(242, 235, 221, 170))
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, "Waiting for camera…")
        p.setClipping(False)
        p.setPen(QPen(QColor(SAND), 4))
        p.drawPath(path)


class ControlBar(_Draggable):
    pause_clicked = Signal()
    draw_clicked = Signal()
    stop_clicked = Signal()
    restart_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("salty-rec-hide-controls")
        self.setObjectName("bar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 10, 10)
        lay.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.time = QLabel("0:00")
        self.time.setObjectName("barTime")
        lay.addWidget(self.dot)
        lay.addWidget(self.time)
        lay.addSpacing(6)
        self.pause = self._btn("Pause", "barGhost", self.pause_clicked)
        self.draw = self._btn("Draw", "barGhost", self.draw_clicked)
        self.draw.setToolTip(f"Draw on screen ({core.MOD}D). Strokes fade after a few seconds.")
        self._btn("Restart", "barGhost", self.restart_clicked)
        self._btn("✕", "barGhost", self.cancel_clicked).setToolTip("Cancel and delete this take")
        self._btn("Stop", "barStop", self.stop_clicked)
        self._blink = True
        self._paused = False
        QTimer(self, interval=600, timeout=self._pulse).start()
        self._pulse()
        self.adjustSize()

    def _btn(self, text, name, signal):
        b = QPushButton(text)
        b.setObjectName(name)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(signal.emit)
        self.layout().addWidget(b)
        return b

    def _pulse(self):
        self._blink = not self._blink
        color = "#8A9799" if self._paused else (CORAL if self._blink else "#7a3a31")
        self.dot.setStyleSheet(f"background:{color};border-radius:5px;")

    def set_paused(self, paused):
        self._paused = paused
        self.pause.setText("Resume" if paused else "Pause")
        self._pulse()

    def set_drawing(self, on):
        self.draw.setText("Done" if on else "Draw")

    def set_time(self, ms):
        s = ms // 1000
        self.time.setText(f"{s // 60}:{s % 60:02d}")

    def place_default(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(g.center().x() - self.width() // 2, g.bottom() - self.height() - 28)

    def showEvent(self, e):
        super().showEvent(e)
        osui.float_everywhere(self)
        osui.hide_from_capture(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(INK))
        p.setPen(QPen(QColor(242, 235, 221, 40), 1))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)


class Countdown(QWidget):
    finished = Signal()
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, FLOAT)
        self.setWindowTitle("salty-rec-hide-countdown")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.resize(220, 220)
        self.n = 3
        self.timer = QTimer(self, interval=1000, timeout=self._tick)

    def run(self):
        self.n = 3
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.center() - QPoint(110, 110))
        self.show()
        self.raise_()
        self.activateWindow()
        osui.float_everywhere(self)
        osui.hide_from_capture(self)
        self.timer.start()
        self.update()

    def _tick(self):
        self.n -= 1
        if self.n == 0:
            self.timer.stop()
            self.hide()
            # give the window server a beat to remove the countdown before capture starts
            QTimer.singleShot(150, self.finished.emit)
        else:
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.timer.stop()
            self.hide()
            self.cancelled.emit()

    def mousePressEvent(self, e):
        self.timer.stop()
        self.hide()
        self.cancelled.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(28, 43, 46, 225))
        p.setPen(Qt.NoPen)
        p.drawEllipse(self.rect().adjusted(4, 4, -4, -4))
        p.setPen(QColor(SAND))
        f = QFont("Space Grotesk", 96)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(self.rect().adjusted(0, -8, 0, -8), Qt.AlignCenter, str(self.n))
        p.setPen(QColor(242, 235, 221, 140))
        f2 = QFont("JetBrains Mono", 10)
        p.setFont(f2)
        p.drawText(self.rect().adjusted(0, 0, 0, -34), Qt.AlignHCenter | Qt.AlignBottom, "ESC OR CLICK TO CANCEL")


class DrawOverlay(QWidget):
    """Transparent layer over the recorded screen. Strokes are captured in the video and fade out on their own."""
    HOLD, FADE = 2.6, 0.6
    exited = Signal()

    def __init__(self):
        super().__init__(None, FLOAT)
        self.setWindowTitle("Salty Rec drawing")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.strokes = []          # [points, finished_at or None]
        self.active = False
        self.color = QColor(CORAL)
        self.timer = QTimer(self, interval=33, timeout=self._tick)

    def cover(self, screen):
        self.setGeometry(screen.geometry())

    def set_active(self, on: bool):
        self.active = on
        if on:
            self.show()
            osui.float_everywhere(self)
            osui.set_level(self, 24)          # under the bubble and controls
            osui.ignore_mouse(self, False)
            self.setCursor(Qt.CrossCursor)
            self.raise_()
            self.activateWindow()
        else:
            osui.ignore_mouse(self, True)
            self.unsetCursor()
            if not self.strokes:
                self.hide()

    def clear(self):
        self.strokes.clear()
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.clear()
            return
        self.strokes.append([[e.position()], None])
        self.timer.start()

    def mouseMoveEvent(self, e):
        if self.strokes and self.strokes[-1][1] is None:
            self.strokes[-1][0].append(e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        if self.strokes and self.strokes[-1][1] is None:
            self.strokes[-1][1] = time.monotonic()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.exited.emit()

    def _tick(self):
        now = time.monotonic()
        self.strokes = [s for s in self.strokes if s[1] is None or now - s[1] < self.HOLD + self.FADE]
        self.update()
        if not self.strokes:
            self.timer.stop()
            if not self.active:
                self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.active:
            p.fillRect(self.rect(), QColor(0, 0, 0, 1))   # keeps clicks on this layer
        now = time.monotonic()
        for pts, done in self.strokes:
            alpha = 1.0 if done is None else max(0.0, min(1.0, 1 - (now - done - self.HOLD) / self.FADE))
            c = QColor(self.color)
            c.setAlphaF(alpha)
            pen = QPen(c, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            if len(pts) == 1:
                p.drawPoint(pts[0])
                continue
            path = QPainterPath(pts[0])
            for a, b in zip(pts, pts[1:]):
                path.quadTo(a, QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
            path.lineTo(pts[-1])
            p.drawPath(path)
