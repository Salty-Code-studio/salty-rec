"""Salty Rec: record panel, recording flow, global shortcuts, menu bar icon."""
import subprocess
import sys

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import core, osui
from .library import Job, Library
from .overlays import CameraBubble, ControlBar, Countdown, DrawOverlay
from .recorder import Recorder
from .theme import QSS

M = core.MOD
SHORTCUTS = f"{M}R start or stop  ·  {M}P pause  ·  {M}D draw  ·  {M}X cancel"


def seg_group(options, current):
    box = QWidget()
    box.setObjectName("segbox")
    lay = QHBoxLayout(box)
    lay.setContentsMargins(3, 3, 3, 3)
    lay.setSpacing(3)
    group = QButtonGroup(box)
    for value, text in options:
        b = QPushButton(text)
        b.setObjectName("seg")
        b.setCheckable(True)
        b.setChecked(value == current)
        b.setProperty("value", value)
        b.setCursor(Qt.PointingHandCursor)
        group.addButton(b)
        lay.addWidget(b)
    if group.checkedButton() is None:
        group.buttons()[0].setChecked(True)
    return box, group


def label(text):
    l = QLabel(text.upper())
    l.setObjectName("label")
    return l


class Panel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("root")
        self.setWindowTitle("Salty Rec")
        self.setFixedWidth(380)
        self.cfg = QSettings("Salty Code", "Salty Rec")

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 22)
        v.setSpacing(8)
        top = QHBoxLayout()
        brand = QLabel("~< salty rec")
        brand.setObjectName("brand")
        lib = QPushButton("Library")
        lib.clicked.connect(lambda: app.show_library())
        top.addWidget(brand)
        top.addStretch()
        top.addWidget(lib)
        v.addLayout(top)
        v.addSpacing(6)

        card = QFrame()
        card.setObjectName("card")
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 16, 16, 16)
        c.setSpacing(6)

        c.addWidget(label("Record"))
        box, self.mode = seg_group([("both", "Screen + cam"), ("screen", "Screen"), ("cam", "Cam")],
                                   self.cfg.value("mode", "both"))
        self.mode.buttonClicked.connect(self._mode_changed)
        c.addWidget(box)

        self.screen_lab, self.screen = label("Screen"), QComboBox()
        self.cam_lab, self.cam = label("Camera"), QComboBox()
        self.mic_lab, self.mic = label("Microphone"), QComboBox()
        for lab, combo in ((self.screen_lab, self.screen), (self.cam_lab, self.cam), (self.mic_lab, self.mic)):
            c.addSpacing(4)
            c.addWidget(lab)
            c.addWidget(combo)
        self.cam.currentIndexChanged.connect(lambda: app.bubble.set_camera(self.cam.currentText()))

        self.size_lab = label("Bubble")
        c.addSpacing(4)
        c.addWidget(self.size_lab)
        self.size_box, self.size = seg_group([("S", "Small"), ("M", "Medium"), ("L", "Large")],
                                             self.cfg.value("size", "M"))
        self.size.buttonClicked.connect(lambda b: app.bubble.set_size(b.property("value")))
        c.addWidget(self.size_box)
        self.shape_box, self.shape = seg_group(list(CameraBubble.SHAPES.items()), self.cfg.value("shape", "round"))
        self.shape.buttonClicked.connect(lambda b: app.bubble.set_shape(b.property("value")))
        c.addWidget(self.shape_box)

        c.addSpacing(8)
        self.system = QCheckBox("Include computer sound")
        self.system.setToolTip(f"Records what {core.MACHINE} plays: a video, a call, a demo with sound.")
        self.system.setChecked(self.cfg.value("system", "false") == "true")
        c.addWidget(self.system)
        self.auto_tx = QCheckBox("Transcribe when I stop")
        self.auto_tx.setChecked(self.cfg.value("auto_tx", "true") == "true")
        c.addWidget(self.auto_tx)
        v.addWidget(card)

        v.addSpacing(6)
        self.rec = QPushButton("●  Start recording")
        self.rec.setObjectName("record")
        self.rec.setCursor(Qt.PointingHandCursor)
        self.rec.clicked.connect(app.begin)
        v.addWidget(self.rec)
        hint = QLabel(SHORTCUTS)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 11px;")
        v.addWidget(hint)
        QShortcut(QKeySequence("Ctrl+R"), self, app.begin)

        self.load_devices()
        self._mode_changed()

    def load_devices(self):
        native = core.helper_devices()
        self.displays = native.get("displays", [])   # cached: a second capture client mid-recording breaks the stream
        screens_ff, cams, mics_ff = core.list_devices()
        self._ff_mics = {name: idx for idx, name in mics_ff}
        displays = [(d["id"], d["name"]) for d in native.get("displays", [])] or \
                   [(i, n.replace("Capture screen ", "Display ")) for i, n in screens_ff]
        if osui.IS_WIN:
            displays = [(i, f"{'Main screen' if i == 0 else 'Screen'} ({s.size().width()}×{s.size().height()})")
                        for i, s in enumerate(QGuiApplication.screens())]
        mics = [(m["uid"], m["name"]) for m in native.get("mics", [])] or [(n, n) for _, n in mics_ff]
        fill = [(self.screen, displays, None, "screen"), (self.cam, cams, None, "cam"),
                (self.mic, mics, "No microphone", "mic")]
        for combo, items, none, key in fill:
            combo.blockSignals(True)
            combo.clear()
            if none:
                combo.addItem(none, None)
            for data, name in items:
                combo.addItem(name, data)
            saved = self.cfg.value(key)
            i = combo.findText(saved) if saved else -1
            combo.setCurrentIndex(i if i >= 0 else (1 if none and combo.count() > 1 else 0))
            combo.blockSignals(False)

    def mode_value(self):
        return self.mode.checkedButton().property("value")

    def _mode_changed(self, *_):
        m = self.mode_value()
        multi = self.screen.count() > 1
        self.screen_lab.setVisible(m != "cam" and multi)
        self.screen.setVisible(m != "cam" and multi)
        self.cam_lab.setVisible(m != "screen")
        self.cam.setVisible(m != "screen")
        self.size_lab.setVisible(m == "both")
        self.size_box.setVisible(m == "both")
        self.shape_box.setVisible(m == "both")
        self.system.setVisible(m != "cam")
        self.adjustSize()
        self.app.sync_bubble()

    def capture_options(self):
        mic_name = self.mic.currentText() if self.mic.currentData() is not None else None
        rect = None
        screens = QGuiApplication.screens()
        if osui.IS_WIN and len(screens) > 1 and isinstance(self.screen.currentData(), int):
            s = screens[min(self.screen.currentData(), len(screens) - 1)]
            g, k = s.geometry(), s.devicePixelRatio()   # gdigrab works in physical pixels
            rect = (round(g.x() * k), round(g.y() * k), round(g.width() * k), round(g.height() * k))
        return dict(mode=self.mode_value(), display=self.screen.currentData(), mic_uid=self.mic.currentData(),
                    display_rect=rect,
                    system=self.system.isChecked(), cam=self.cam.currentData(),
                    mic_index=self._ff_mics.get(mic_name) if mic_name else None)

    def save(self):
        self.cfg.setValue("mode", self.mode_value())
        self.cfg.setValue("size", self.size.checkedButton().property("value"))
        self.cfg.setValue("shape", self.shape.checkedButton().property("value"))
        self.cfg.setValue("screen", self.screen.currentText())
        self.cfg.setValue("cam", self.cam.currentText())
        self.cfg.setValue("mic", self.mic.currentText())
        self.cfg.setValue("system", "true" if self.system.isChecked() else "false")
        self.cfg.setValue("auto_tx", "true" if self.auto_tx.isChecked() else "false")

    def showEvent(self, e):
        super().showEvent(e)
        self.app.sync_bubble()

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.app.sync_bubble()


class Hotkeys:
    """Global shortcuts through the native helper (Carbon hot keys need no Accessibility permission)."""

    def __init__(self, handler):
        self.handler = handler
        self.proc = QProcess()
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(lambda code, _s: print(
            f"hotkeys helper exited {code}: {bytes(self.proc.readAllStandardError()).decode(errors='ignore').strip()}",
            flush=True))
        self.proc.errorOccurred.connect(lambda e: print(f"hotkeys helper error {e}", flush=True))
        self.proc.start(str(core.HELPER), ["hotkeys"])

    def _read(self):
        for line in bytes(self.proc.readAllStandardOutput()).decode(errors="ignore").splitlines():
            if line.strip() and line.strip() != "ready":
                self.handler(line.strip())

    def stop(self):
        if self.proc.state() != QProcess.NotRunning:
            self.proc.write(b"q\n")
            self.proc.closeWriteChannel()
            self.proc.waitForFinished(1500)


class SaltyRec:
    def __init__(self):
        osui.brand_process()
        self.qt = QApplication(sys.argv)
        self.qt.setApplicationName("Salty Rec")
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setStyleSheet(QSS)
        icon = QIcon(str(core.ASSETS / "icon.png"))
        self.qt.setWindowIcon(icon)

        self.recorder = Recorder()
        self.bubble = CameraBubble()
        self.bar = ControlBar()
        self.countdown = Countdown()
        self.draw = DrawOverlay()
        self.library = None
        self.jobs = set()
        self._bubble_placed = False
        self._bar_placed = False
        self.panel = Panel(self)
        self.bubble.set_size(self.panel.size.checkedButton().property("value"))
        self.bubble.set_shape(self.panel.shape.checkedButton().property("value"))
        self.bubble.shape_changed.connect(lambda k: self._check_seg(self.panel.shape, k))
        self.bubble.size_changed.connect(lambda k: self._check_seg(self.panel.size, k))
        if osui.IS_MAC:
            self._ask_av_access()

        self.tick = QTimer(interval=250, timeout=lambda: self.bar.set_time(self.recorder.elapsed_ms()))
        self.countdown.finished.connect(self._go)
        self.countdown.cancelled.connect(self._abort_countdown)
        self.bar.pause_clicked.connect(self._pause)
        self.bar.draw_clicked.connect(self.toggle_draw)
        self.bar.stop_clicked.connect(self._stop)
        self.bar.restart_clicked.connect(self._restart)
        self.bar.cancel_clicked.connect(self._cancel)
        self.draw.exited.connect(lambda: self.toggle_draw(False))
        self.recorder.failed.connect(self._failed)
        self.recorder.state_changed.connect(lambda s: self.bar.set_paused(s == "paused"))

        self.tray = QSystemTrayIcon(icon)
        menu = QMenu()
        self.a_rec = QAction(f"Start recording  {M}R", menu, triggered=self._toggle_record)
        menu.addAction(self.a_rec)
        menu.addAction(QAction("Open library", menu, triggered=lambda: self.show_library()))
        menu.addAction(QAction("Show recorder", menu, triggered=self.show_panel))
        menu.addSeparator()
        menu.addAction(QAction("Quit Salty Rec", menu, triggered=self.quit))
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Salty Rec")
        self.tray.show()
        self.qt.applicationStateChanged.connect(self._activated)
        if osui.IS_WIN:
            from .winkeys import WinHotkeys
            self.hotkeys = WinHotkeys(self._hotkey)
        else:
            self.hotkeys = Hotkeys(self._hotkey)
        self.qt.aboutToQuit.connect(self.hotkeys.stop)

    # ---------- windows ----------
    def show_panel(self):
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def show_library(self, select=None):
        if self.library is None:
            self.library = Library()
            self.library.record_requested.connect(self.show_panel)
        self.library.refresh(select)
        self.library.show()
        self.library.raise_()
        self.library.activateWindow()

    @staticmethod
    def _check_seg(group, value):
        for b in group.buttons():
            if b.property("value") == value:
                b.setChecked(True)

    def _ask_av_access(self):
        """Ask macOS for camera and mic up front, so the bubble shows you instead of staying dark.
        The helper asks, because Qt can't from a Python that lives outside the app bundle."""
        self._av = QProcess()
        self._av.finished.connect(lambda *_: self.bubble.set_camera(self.panel.cam.currentText()))
        self._av.start(str(core.HELPER), ["av-permission"])

    def sync_bubble(self):
        if not hasattr(self, "panel"):
            return
        idle_preview = self.panel.isVisible() and self.panel.mode_value() != "screen" and self.recorder.state == "idle"
        recording_with_cam = self.recorder.state != "idle" and self.recorder.mode == "both"
        if idle_preview or recording_with_cam:
            self._show_bubble()
        else:
            self.bubble.hide()

    def _show_bubble(self):
        if not self._bubble_placed:
            self.bubble.place_default()
            self._bubble_placed = True
        if not self.bubble.isVisible():
            self.bubble.show()

    def _activated(self, state):
        if state == Qt.ApplicationActive and self.recorder.state == "idle" and not self.countdown.isVisible():
            if not self.panel.isVisible() and not (self.library and self.library.isVisible()):
                self.show_panel()

    def _screen_for_display(self):
        """The Qt screen that matches the display being recorded."""
        did = self.panel.screen.currentData()
        for d in self.panel.displays:
            if d["id"] == did:
                for s in QGuiApplication.screens():
                    if abs(s.geometry().x() - d["x"]) < 2 and abs(s.geometry().y() - d["y"]) < 2:
                        return s
        return QGuiApplication.primaryScreen()

    # ---------- shortcuts ----------
    def _hotkey(self, name):
        if name == "record":
            self._toggle_record()
        elif name == "pause":
            self._pause()
        elif name == "draw" and self.recorder.state != "idle":
            self.toggle_draw()
        elif name == "cancel" and self.recorder.state != "idle":
            self._cancel()

    def _toggle_record(self):
        if self.recorder.state == "idle":
            self.begin()
        else:
            self._stop()

    def toggle_draw(self, on=None):
        on = (not self.draw.active) if on is None else on
        if on and self.recorder.mode == "cam":
            return
        if on:
            self.draw.cover(self._screen_for_display())
        self.draw.set_active(on)
        self.bar.set_drawing(on)
        if on:
            self.bubble.raise_()
            self.bar.raise_()

    # ---------- recording flow ----------
    def begin(self):
        if self.recorder.state != "idle" or self.countdown.isVisible():
            return
        p = self.panel
        p.save()
        opts = p.capture_options()
        if osui.IS_MAC and opts["mode"] != "cam" and not self._screen_access():
            return
        self.recorder.configure(**opts)
        p.hide()
        if opts["mode"] == "both":
            self._show_bubble()
        else:
            self.bubble.hide()       # camera-only: ffmpeg needs the camera to itself
        self.bar.winId()             # native window must exist so capture can leave it out
        self.recorder.prepare()      # warm up capture during the countdown
        self.countdown.run()

    def _abort_countdown(self):
        self.recorder.abort_prepare()
        self.show_panel()

    def _go(self):
        if not self._bar_placed:
            self.bar.place_default()
            self._bar_placed = True
        self.bar.set_time(0)
        self.bar.set_paused(False)
        self.bar.show()
        self._start_capture()

    def _start_capture(self):
        self.recorder.start(core.new_workdir())
        self.tick.start()
        self.a_rec.setText(f"Stop recording  {M}R")

    def _pause(self):
        if self.recorder.state == "recording":
            self.recorder.pause()
        elif self.recorder.state == "paused":
            self.recorder.resume()

    def _end_ui(self):
        self.tick.stop()
        self.toggle_draw(False)
        self.draw.clear()
        self.draw.hide()
        self.bar.hide()
        self.a_rec.setText(f"Start recording  {M}R")

    def _stop(self):
        if self.recorder.state == "idle":
            return
        folder = self.recorder.workdir
        segments = self.recorder.stop()
        self._end_ui()
        self.bubble.hide()
        auto_tx = self.panel.auto_tx.isChecked()
        self.show_library()
        self.library.status.setText("Saving your recording…")
        job = Job(core.finalize, folder, segments)

        def ok(f):
            self.jobs.discard(job)
            self.show_library(f)
            self.library.status.setText("Saved. Share link puts a link on your clipboard.")
            if auto_tx:
                self.library.transcribe(f)

        def err(msg):
            self.jobs.discard(job)
            self.library.status.setText(msg)
        job.ok.connect(ok)
        job.err.connect(err)
        self.jobs.add(job)
        job.start()

    def _restart(self):
        self.recorder.cancel()
        self._end_ui()
        self.recorder.prepare()
        self.countdown.run()

    def _cancel(self):
        was = self.recorder.state
        self.recorder.pause()
        if QMessageBox.question(None, "Delete this take?", "This recording will be thrown away.") == QMessageBox.Yes:
            self.recorder.cancel()
            self._end_ui()
            self.show_panel()
        elif was == "recording":
            self.recorder.resume()

    def _screen_access(self):
        try:
            out = subprocess.run([str(core.HELPER), "permission"], capture_output=True, text=True, timeout=20).stdout
        except Exception:
            return True
        if "granted" in out:
            return True
        self._ask_screen_access()
        return False

    def _ask_screen_access(self):
        box = QMessageBox()
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Allow screen recording")
        box.setText("Salty Rec needs permission to record your screen.")
        box.setInformativeText("In the settings window, switch on Salty Rec under Screen & System Audio Recording. "
                               "Then quit Salty Rec from the menu bar and open it again.")
        go = box.addButton("Open Settings", QMessageBox.AcceptRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is go:
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"])

    def _failed(self, msg):
        low = msg.lower()
        if osui.IS_MAC and any(w in low for w in ("tcc", "not authorized", "declined", "afgewezen")):
            self.recorder.cancel()
            self._end_ui()
            self.bubble.hide()
            self._ask_screen_access()
            return
        hint = ""
        if any(w in low for w in ("permission", "input/output")):
            hint = ("\n\nmacOS needs Camera and Microphone access for Salty Rec. "
                    "Turn them on in System Settings › Privacy & Security, then quit and reopen Salty Rec.")
        QMessageBox.warning(None, "Recording paused", f"{msg}{hint}\n\nResume to try again, or Stop to keep what you have.")

    def quit(self):
        if self.recorder.state != "idle":
            self._stop()
        self.qt.quit()

    def run(self):
        self.show_panel()
        QTimer.singleShot(400, self.show_panel)
        return self.qt.exec()


def main():
    sys.exit(SaltyRec().run())
