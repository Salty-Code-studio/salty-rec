"""Library window: play, rename, trim, cut silences, transcripts, share."""
import subprocess
from pathlib import Path

from PySide6.QtCore import QFile, QMimeData, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QSlider, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from . import core, share
from .stage import Stage


def fmt(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class Job(QThread):
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.ok.emit(self.fn(*self.args))
        except Exception as e:
            self.err.emit(str(e))


class Library(QWidget):
    record_requested = Signal()
    _progress = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("library")
        self.setWindowTitle("Salty Rec Library")
        self.resize(1180, 760)
        self.jobs: set[Job] = set()
        self.busy: set[str] = set()
        self.current: Path | None = None
        self.mark_in, self.mark_out = None, None
        self._search_cache: dict[str, str] = {}

        # left column
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(18, 18, 8, 18)
        top = QHBoxLayout()
        brand = QLabel("~< salty rec")
        brand.setObjectName("brand")
        new = QPushButton("New recording")
        new.clicked.connect(self.record_requested.emit)
        top.addWidget(brand)
        top.addStretch()
        top.addWidget(new)
        lv.addLayout(top)
        self.search = QLineEdit(placeholderText="Search titles and what was said")
        self.search.textChanged.connect(self._filter)
        lv.addWidget(self.search)
        self.list = QListWidget()
        self.list.setIconSize(QSize(128, 72))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.currentItemChanged.connect(lambda cur, _: self.open(Path(cur.data(Qt.UserRole))) if cur else None)
        lv.addWidget(self.list, 1)

        # right column
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 18, 18, 18)
        rv.setSpacing(10)
        self.title = QLineEdit()
        self.title.setObjectName("title")
        self.title.setToolTip("Click to rename")
        self.title.editingFinished.connect(self._rename)
        rv.addWidget(self.title)
        # three planes: the length huge at the back, the video in the middle, the next tap on top
        self.video = QVideoWidget()
        self.video.setStyleSheet("background:#1C2B2E;")
        self.b_share = QPushButton("Share link")
        self.b_share.setObjectName("signal")
        self.b_share.setCursor(Qt.PointingHandCursor)
        self.b_share.clicked.connect(self._main_action)
        self.stage = Stage(self.video, self.b_share, back="", huge=150, align_button="right")
        self.stage.setMinimumHeight(420)
        rv.addWidget(self.stage, 3)
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)

        transport = QHBoxLayout()
        self.play = QPushButton("Play")
        self.play.clicked.connect(self._toggle_play)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.sliderMoved.connect(lambda v: self.player.setPosition(v))
        self.clock = QLabel("0:00 / 0:00")
        self.clock.setObjectName("label")
        self.speed = QPushButton("1x")
        self.speed.setToolTip("Playback speed")
        self.speed.clicked.connect(self._cycle_speed)
        transport.addWidget(self.play)
        transport.addWidget(self.seek, 1)
        transport.addWidget(self.clock)
        transport.addWidget(self.speed)
        rv.addLayout(transport)
        self.player.positionChanged.connect(self._pos)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.playbackStateChanged.connect(
            lambda s: self.play.setText("Pause" if s == QMediaPlayer.PlayingState else "Play"))

        links = QHBoxLayout()
        self.b_open = self._btn(links, "Open page", self._open_page)
        self.b_unshare = self._btn(links, "Stop sharing", self._unshare, tip="Deletes the online copy. The link stops working.")
        links.addStretch()
        self.views = QLabel("")
        self.views.setObjectName("label")
        links.addWidget(self.views)
        rv.addLayout(links)

        files = QHBoxLayout()
        self.b_copy = self._btn(files, "Copy video file", self._copy,
                                tip="Copies the file itself. Paste it into WhatsApp, Mail or Slack.")
        self._btn(files, f"Show in {core.FILE_MANAGER}", self._reveal)
        self.b_caps = self._btn(files, "Export with captions", self._captions,
                                tip="MP4 with a subtitle track that QuickTime and most players show.")
        files.addStretch()
        self._btn(files, "Delete", self._delete, "danger")
        rv.addLayout(files)

        edit = QHBoxLayout()
        lab = QLabel("EDIT")
        lab.setObjectName("label")
        edit.addWidget(lab)
        self._btn(edit, "Start here", self._mark_in, tip="Set the trim start at the playhead")
        self._btn(edit, "End here", self._mark_out, tip="Set the trim end at the playhead")
        self.b_trim = self._btn(edit, "Trim", self._trim)
        self.b_sil = self._btn(edit, "Remove silences", self._silences,
                               tip="Cuts every pause longer than 0.7 seconds")
        self.b_ums = self._btn(edit, "Remove ums", self._fillers,
                               tip="Cuts every um and uh. Transcribes first if needed, all on this device.")
        self.b_undo = self._btn(edit, "Undo edits", self._undo, tip="Back to the original take")
        edit.addStretch()
        self.marks = QLabel("")
        self.marks.setObjectName("muted")
        edit.addWidget(self.marks)
        rv.addLayout(edit)

        th = QHBoxLayout()
        lab2 = QLabel("TRANSCRIPT")
        lab2.setObjectName("label")
        th.addWidget(lab2)
        th.addStretch()
        self.b_tx = QPushButton("Transcribe")
        self.b_tx.clicked.connect(self._transcribe)
        th.addWidget(self.b_tx)
        rv.addLayout(th)
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.anchorClicked.connect(self._jump)
        rv.addWidget(self.transcript, 2)
        self.status = QLabel("")
        self.status.setObjectName("status")
        rv.addWidget(self.status)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([360, 820])
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(split)
        self.right = right
        self._progress.connect(self.status.setText)
        self.refresh()

    # ---------- list ----------
    def _btn(self, layout, text, fn, name=None, tip=None):
        b = QPushButton(text)
        if name:
            b.setObjectName(name)
        if tip:
            b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        layout.addWidget(b)
        return b

    def refresh(self, select: Path | None = None):
        keep = select or self.current
        self.list.blockSignals(True)
        self.list.clear()
        self._search_cache.clear()
        for folder in core.recordings():
            meta = core.read_meta(folder)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, str(folder))
            when = meta.get("created", "")[:16].replace("T", "  ")
            item.setText(f"{meta['title']}\n{fmt(meta.get('duration', 0))}   ·   {when}")
            thumb = folder / "thumb.jpg"
            if thumb.exists():
                item.setIcon(QIcon(QPixmap(str(thumb))))
            self.list.addItem(item)
            if keep and folder == keep:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self._filter(self.search.text())
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        elif keep and self.list.currentItem():
            self.open(Path(self.list.currentItem().data(Qt.UserRole)))
        self.right.setEnabled(self.list.count() > 0)
        if not self.list.count():
            self.title.setText("No recordings yet")

    def _filter(self, q):
        q = q.lower().strip()
        for i in range(self.list.count()):
            it = self.list.item(i)
            folder = Path(it.data(Qt.UserRole))
            if q and str(folder) not in self._search_cache:
                tx = folder / "transcript.txt"
                self._search_cache[str(folder)] = (it.text() + " " + (tx.read_text() if tx.exists() else "")).lower()
            it.setHidden(bool(q) and q not in self._search_cache.get(str(folder), ""))

    # ---------- detail ----------
    def open(self, folder: Path):
        if self.current != folder:
            self.mark_in = self.mark_out = None
        self.current = folder
        meta = core.read_meta(folder)
        self.title.setText(meta["title"])
        self.stage.set_back(fmt(meta.get("duration", 0)))
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(folder / "video.mp4")))
        self._render_transcript()
        self._update_marks()
        self._sync_buttons()
        self._load_views(folder)

    def _render_transcript(self):
        rows = core.parse_srt(self.current / "transcript.srt")
        if not rows:
            busy = f"tx:{self.current}" in self.busy
            self.transcript.setHtml(f"<p style='color:rgba(28,43,46,.6)'>"
                                    f"{f'Transcribing on {core.MACHINE}. This can take a minute.' if busy else 'No transcript yet.'}</p>")
            return
        html = "".join(f"<p style='margin:0 0 6px'><a href='t:{t}' style='color:#4FA8C9;text-decoration:none;"
                       f"font-family:JetBrains Mono'>{fmt(t)}</a>&nbsp;&nbsp;{txt}</p>" for t, txt in rows)
        self.transcript.setHtml(html)

    def _jump(self, url: QUrl):
        s = url.toString()
        if s.startswith("t:"):
            self.player.setPosition(int(float(s[2:]) * 1000))
            self.player.play()

    def _pos(self, ms):
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self.clock.setText(f"{fmt(ms / 1000)} / {fmt(self.player.duration() / 1000)}")

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _cycle_speed(self):
        rates = [1.0, 1.25, 1.5, 2.0]
        r = rates[(rates.index(self.player.playbackRate()) + 1) % len(rates)] if self.player.playbackRate() in rates else 1.0
        self.player.setPlaybackRate(r)
        self.speed.setText(f"{r:g}x")

    def _rename(self):
        if self.current and self.title.text().strip():
            core.write_meta(self.current, title=self.title.text().strip(), title_auto=False)
            item = self.list.currentItem()
            if item:
                lines = item.text().split("\n")
                item.setText(self.title.text().strip() + "\n" + (lines[1] if len(lines) > 1 else ""))
            self._push_meta(self.current)

    # ---------- actions ----------
    def _copy(self):
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(str(self.current / "video.mp4"))])
        QGuiApplication.clipboard().setMimeData(m)
        self.status.setText("Copied. Paste it anywhere a file can go.")

    def _reveal(self):
        core.reveal(self.current / "video.mp4")

    def _delete(self):
        meta = core.read_meta(self.current)
        if QMessageBox.question(self, f"Move to {core.TRASH}",
                                f"Move “{meta['title']}” to the {core.TRASH}?") != QMessageBox.Yes:
            return
        self.player.setSource(QUrl())
        if core.read_meta(self.current).get("share_id"):
            try:
                share.unpublish(self.current)
            except Exception:
                pass
        res = QFile.moveToTrash(str(self.current))
        if not (res[0] if isinstance(res, tuple) else res) and not core.IS_WIN:
            subprocess.run(["osascript", "-e", f'tell app "Finder" to delete POSIX file "{self.current}"'])
        self.current = None
        self.refresh()
        self.status.setText(f"Moved to the {core.TRASH}. You can put it back from there.")

    # ---------- share links ----------
    def _share(self):
        folder = self.current
        st = share.state(folder)
        if st == "live":
            self._copy_link(core.read_meta(folder)["share_url"])
            return
        if st == "stale-meta":
            self._run(f"share:{folder}", "Updating the shared page", share.update_meta, folder,
                      ok=lambda url: (self._copy_link(url), self._sync_buttons()))
            return
        job_key = f"share:{folder}"

        def progress(pct):
            # runs on the worker thread; QLabel.setText is queued safely through the signal below
            self._progress.emit(f"Uploading {pct}%")
        self._run(job_key, "Preparing a light copy for sharing", share.publish, folder, progress,
                  ok=lambda url: (self._copy_link(url), self._sync_buttons()))

    def _copy_link(self, url):
        QGuiApplication.clipboard().setText(url)
        self.status.setText(f"Link copied: {url}")

    def _open_page(self):
        url = core.read_meta(self.current).get("share_url")
        if url:
            share.open_in_browser(url)

    def _unshare(self):
        if QMessageBox.question(self, "Stop sharing", "Delete the online copy? Anyone with the link loses access.") != QMessageBox.Yes:
            return
        folder = self.current
        self._run(f"share:{folder}", "Removing the online copy", share.unpublish, folder,
                  ok=lambda _: (self.status.setText("Link turned off."), self._sync_buttons()))

    def _push_meta(self, folder):
        if folder and share.state(folder) == "stale-meta":
            self._run(f"share:{folder}", "Updating the shared page", share.update_meta, folder,
                      ok=lambda _: self.status.setText("Shared page updated."))

    def _load_views(self, folder):
        self.views.setText("")
        if not core.read_meta(folder).get("share_id"):
            return
        job = Job(share.stats, folder)

        def ok(st):
            self.jobs.discard(job)
            if st and folder == self.current:
                n = st.get("views", 0)
                self.views.setText(f"{n} VIEW{'S' if n != 1 else ''}")
        job.ok.connect(ok)
        job.err.connect(lambda _: self.jobs.discard(job))
        self.jobs.add(job)
        job.start()

    def _mark_in(self):
        self.mark_in = self.player.position() / 1000
        self._update_marks()

    def _mark_out(self):
        self.mark_out = self.player.position() / 1000
        self._update_marks()

    def _update_marks(self):
        if self.mark_in is None and self.mark_out is None:
            self.marks.setText("")
        else:
            a = fmt(self.mark_in) if self.mark_in is not None else "start"
            b = fmt(self.mark_out) if self.mark_out is not None else "end"
            self.marks.setText(f"Keep {a} to {b}")

    def _trim(self):
        if self.mark_in is None and self.mark_out is None:
            self.status.setText("Move the playhead, then press Start here and End here.")
            return
        end = self.mark_out if self.mark_out is not None else self.player.duration() / 1000
        start = self.mark_in or 0.0
        self._edit("Trimming", core.trim, start, end, done="Trimmed. Undo edits brings the original back.")

    def _silences(self):
        def after(cut):
            return f"Removed {cut:.1f} seconds of silence." if cut else "No long silences found."
        self._edit("Cutting silences", core.remove_silences, done=after)

    def _fillers(self):
        def after(n):
            return f"Cut {n} um{'s' if n != 1 else ''} and uh{'s' if n != 1 else ''}." if n else "No ums or uhs found."
        self._edit("Cutting ums", core.remove_fillers, done=after)

    def _undo(self):
        self._edit("Restoring original", core.restore_original, done="Original take restored.")

    def _edit(self, label, fn, *args, done):
        folder = self.current
        self.player.stop()
        self.player.setSource(QUrl())
        self.mark_in = self.mark_out = None

        def ok(result):
            self.status.setText(done(result) if callable(done) else done)
            self.refresh(folder)
        self._run(f"edit:{folder}", label, fn, folder, *args, ok=ok, fail=lambda: self.open(folder))

    def _transcribe(self):
        folder = self.current
        self.transcribe(folder)

    def transcribe(self, folder: Path):
        def ok(_):
            self.status.setText("Transcript ready. Click a timestamp to jump there.")
            self.refresh(folder)
            self._push_meta(folder)
        self._run(f"tx:{folder}", "Transcribing", core.transcribe, folder, ok=ok)
        if folder == self.current:
            self._render_transcript()

    def _captions(self):
        folder = self.current
        self._run(f"cap:{folder}", "Exporting with captions", core.export_with_captions, folder,
                  ok=lambda out: (core.reveal(out),
                                  self.status.setText("Exported next to the original."), self.refresh(folder)))

    def _run(self, key, label, fn, *args, ok, fail=None):
        if key in self.busy:
            return
        self.busy.add(key)
        self.status.setText(f"{label}…")
        self._sync_buttons()
        job = Job(fn, *args)

        def finish():
            self.busy.discard(key)
            self.jobs.discard(job)
            self._sync_buttons()

        def on_ok(r):
            finish()
            ok(r)

        def on_err(msg):
            finish()
            self.status.setText(msg)
            if fail:
                fail()
        job.ok.connect(on_ok)
        job.err.connect(on_err)
        self.jobs.add(job)
        job.start()

    def _main_action(self):
        if share.configured():
            self._share()
        else:
            self._copy()

    def _sync_buttons(self):
        if not self.current:
            return
        c = str(self.current)
        editing = f"edit:{c}" in self.busy
        tx = f"tx:{c}" in self.busy
        for b in (self.b_trim, self.b_sil, self.b_ums, self.b_undo):
            b.setEnabled(not editing and not tx)
        self.b_undo.setEnabled(not editing and not tx and (self.current / "original.mp4").exists())
        self.b_tx.setEnabled(not tx and not editing)
        self.b_tx.setText("Transcribing…" if tx else
                          ("Transcribe again" if (self.current / "transcript.srt").exists() else "Transcribe"))
        self.b_caps.setEnabled(not editing and f"cap:{c}" not in self.busy)
        self.b_copy.setEnabled(not editing)
        sharing = f"share:{c}" in self.busy
        st = share.state(self.current)
        self.b_share.setEnabled(not editing and not sharing)
        self.b_share.setText("Sharing…" if sharing else {"none": "Share link", "live": "Copy link",
                                                        "stale-video": "Update link", "stale-meta": "Copy link"}[st])
        self.b_open.setVisible(st != "none")
        self.b_unshare.setVisible(st != "none")
        self.b_unshare.setEnabled(not sharing)
        self.b_share.setToolTip("Uploads a light copy and puts a private link on your clipboard.")
        if not share.configured():          # without a share server the next tap is copying the file
            self.b_share.setText("Copy video file")
            self.b_share.setToolTip("Copies the file itself. Paste it into WhatsApp, Mail or Slack.")
            self.b_share.setEnabled(not editing)
            for w in (self.b_open, self.b_unshare, self.views):
                w.setVisible(False)
        self.b_copy.setVisible(share.configured())

    def closeEvent(self, e):
        self.player.pause()
        super().closeEvent(e)
