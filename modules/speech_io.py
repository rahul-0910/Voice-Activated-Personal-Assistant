"""
speech_io.py
------------
Wraps speech-to-text (SpeechRecognition) and text-to-speech (pyttsx3).

Both `TextToSpeech` and `SpeechRecognizer` probe their underlying hardware
at construction time and raise `HardwareUnavailableError` if no
speakers/microphone can be found. `assistant.py` catches that and drops to
typed-text mode automatically, so the app never just crashes on a headless
machine or a laptop with no mic permissions granted.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Optional

logger = logging.getLogger("assistant.speech_io")


class SpeechError(Exception):
    """Raised when a single listen/speak attempt fails (recoverable)."""


class HardwareUnavailableError(Exception):
    """Raised at startup when no working microphone or audio output device is found."""


class TextToSpeech:
    """
    Thread-safe wrapper around pyttsx3. All speech requests run on a single
    dedicated worker thread via a queue of callables, since pyttsx3's
    engine.runAndWait() isn't safe to call concurrently.
    """

    def __init__(self, rate: int = 180, volume: float = 1.0, voice_index: Optional[int] = None):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            # Touching getProperty forces pyttsx3 to actually resolve a driver;
            # on a machine with no audio output this is where it tends to fail.
            voices = self._engine.getProperty("voices")
            if not voices:
                raise HardwareUnavailableError("No TTS voices available on this system.")
        except HardwareUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HardwareUnavailableError(f"Could not initialize text-to-speech engine: {exc}") from exc

        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)
        if voice_index is not None and 0 <= voice_index < len(voices):
            self._engine.setProperty("voice", voices[voice_index].id)

        self._queue: "queue.Queue[Optional[Callable[[], None]]]" = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        while True:
            job = self._queue.get()
            if job is None:  # poison pill -> shut down
                break
            try:
                job()
            except Exception:  # noqa: BLE001 - never let TTS crash the assistant
                logger.exception("TTS engine failed while running a speech job")

    def say(self, text: str, block: bool = False):
        """Print + queue text to be spoken. If block=True, wait until spoken aloud."""
        print(f"[assistant] {text}")

        def _speak():
            self._engine.say(text)
            self._engine.runAndWait()

        if not block:
            self._queue.put(_speak)
            return

        done = threading.Event()

        def _speak_then_signal():
            try:
                _speak()
            finally:
                done.set()

        self._queue.put(_speak_then_signal)
        done.wait()

    def shutdown(self):
        self._queue.put(None)


class SpeechRecognizer:
    """
    Thin wrapper around `speech_recognition`. Uses the default microphone
    and Google's free web speech API for recognition. Swap out
    `recognize_google` for an offline engine (Vosk, Whisper, etc.) without
    changing any calling code.
    """

    def __init__(self, energy_threshold: int = 300, pause_threshold: float = 0.8,
                 ambient_calibration_seconds: float = 1.0):
        try:
            import speech_recognition as sr
        except ImportError as exc:
            raise HardwareUnavailableError(f"speech_recognition is not installed: {exc}") from exc

        self._sr = sr
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = energy_threshold
        self._recognizer.pause_threshold = pause_threshold

        try:
            self._mic = sr.Microphone()
            # Actually open the audio stream once to confirm a mic exists and
            # is accessible, rather than waiting for the first real listen().
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.1)
        except (OSError, AttributeError, IndexError) as exc:
            raise HardwareUnavailableError(f"No usable microphone found: {exc}") from exc

        self._calibration_seconds = ambient_calibration_seconds
        self._calibrated = True  # already calibrated briefly above

    def calibrate(self, duration: Optional[float] = None):
        with self._mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=duration or self._calibration_seconds)
        self._calibrated = True

    def listen_once(self, timeout: Optional[float] = 5.0, phrase_time_limit: Optional[float] = 8.0) -> str:
        """
        Block until the user says something (or times out), then return the
        recognized text (lowercased is NOT applied here — callers decide).
        Raises SpeechError on failure so callers can decide how to react.
        """
        with self._mic as source:
            try:
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except self._sr.WaitTimeoutError as exc:
                raise SpeechError("Listening timed out with no speech detected.") from exc

        try:
            text = self._recognizer.recognize_google(audio)
        except self._sr.UnknownValueError as exc:
            raise SpeechError("Could not understand audio.") from exc
        except self._sr.RequestError as exc:
            raise SpeechError(f"Speech recognition service error: {exc}") from exc

        logger.info("Recognized: %s", text)
        return text


def probe_hardware(tts_rate: int = 180) -> bool:
    """
    Try to construct both a TextToSpeech engine and a SpeechRecognizer.
    Returns True if voice mode is fully usable, False otherwise. Used by
    assistant.py to decide whether to auto-fallback to typed text.
    """
    try:
        tts = TextToSpeech(rate=tts_rate)
        tts.shutdown()
        SpeechRecognizer()
        return True
    except HardwareUnavailableError as exc:
        logger.warning("Voice hardware unavailable, will fall back to text mode: %s", exc)
        return False
