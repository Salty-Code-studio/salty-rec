"""Windows computer sound: WASAPI loopback of the default speaker, written to a WAV per segment.
Windows sends no audio packets while nothing plays, so silence is padded from the wall clock
to keep the track the same length as the video."""
import threading
import time
import wave
from pathlib import Path

RATE, CHANNELS, CHUNK = 48000, 2, 2400     # 50 ms reads


class Loopback:
    def __init__(self, out: Path):
        self.out = out
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.error = None

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self):
        try:
            import numpy as np
            import soundcard as sc
            speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            with wave.open(str(self.out), "wb") as w, mic.recorder(samplerate=RATE, channels=CHANNELS) as rec:
                w.setnchannels(CHANNELS)
                w.setsampwidth(2)
                w.setframerate(RATE)
                t0, written = time.monotonic(), 0
                while not self._stop.is_set():
                    data = rec.record(numframes=CHUNK)
                    behind = int((time.monotonic() - t0) * RATE) - written - len(data)
                    if behind > CHUNK:                     # Windows skipped silence
                        w.writeframes(np.zeros((behind, CHANNELS), dtype=np.int16).tobytes())
                        written += behind
                    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
                    w.writeframes(pcm.tobytes())
                    written += len(pcm)
        except Exception as e:      # no speaker, driver refuses loopback: record without computer sound
            self.error = str(e)
