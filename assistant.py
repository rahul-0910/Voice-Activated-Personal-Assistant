#!/usr/bin/env python3
"""
assistant.py
------------
Main loop for the voice assistant: wake-word detection + intent routing.

Usage:
    python assistant.py                # voice mode if mic/speakers are found,
                                        # otherwise auto-falls back to typed text
    python assistant.py --text         # force typed text mode
    python assistant.py --no-wake-word # process every utterance, skip the wake word
    python assistant.py --location "Paris" --units imperial

By default you need to say the wake word ("assistant" — configurable via
ASSISTANT_WAKE_WORD) before a command, e.g.:
    "assistant, what's the weather in Tokyo"
    "assistant, remind me to call mom in 20 minutes"
"""

from __future__ import annotations

import argparse
import logging
import re
import sys

from modules import config
from modules.intents import IntentContext, IntentRouter
from modules.reminders import ReminderManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("assistant.main")


def parse_args():
    parser = argparse.ArgumentParser(description="Personal voice assistant")
    parser.add_argument("--text", action="store_true", help="Force typed text mode instead of voice.")
    parser.add_argument("--no-wake-word", action="store_true",
                         help="Skip wake-word detection; treat every utterance as a command.")
    parser.add_argument("--wake-word", default=config.WAKE_WORD, help="Wake word to listen for.")
    parser.add_argument("--location", default=config.DEFAULT_LOCATION, help="Default location for weather queries.")
    parser.add_argument("--units", choices=["metric", "imperial"], default=config.UNITS)
    parser.add_argument("--rate", type=int, default=config.TTS_RATE, help="TTS speaking rate (words/min).")
    parser.add_argument("--no-speak", action="store_true",
                         help="Print responses instead of speaking them (useful without speakers).")
    return parser.parse_args()


class PrintOnlyTTS:
    """Fallback TTS used with --no-speak or when no audio output is available."""

    def say(self, text: str, block: bool = False):
        print(f"[assistant] {text}")

    def shutdown(self):
        pass


def build_tts(rate: int, disabled: bool):
    if disabled:
        return PrintOnlyTTS()
    from modules.speech_io import HardwareUnavailableError, TextToSpeech
    try:
        return TextToSpeech(rate=rate)
    except HardwareUnavailableError as exc:
        logger.warning("No audio output available (%s); printing responses instead.", exc)
        return PrintOnlyTTS()


def strip_wake_word(text: str, wake_word: str) -> "tuple[bool, str]":
    """
    Returns (matched, remainder). Matches "assistant", "assistant,", "hey
    assistant", "assistant what's the weather", etc. at the start of the
    utterance, case-insensitively.
    """
    pattern = re.compile(rf"^\s*(hey\s+)?{re.escape(wake_word)}\b[,\s]*", re.IGNORECASE)
    match = pattern.match(text)
    if not match:
        return False, text
    return True, text[match.end():].strip()


def run_text_mode(router: IntentRouter, tts) -> None:
    print("Text mode. Type a command, or 'exit' to quit.")
    print("(No wake word needed when typing — just type your command directly.)")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if router.is_exit_command(text):
            tts.say("Goodbye!", block=True)
            break

        response = router.handle(text)
        tts.say(response)


def run_voice_mode(router: IntentRouter, tts, wake_word: str, require_wake_word: bool) -> None:
    from modules.speech_io import SpeechError, SpeechRecognizer

    recognizer = SpeechRecognizer()  # probing already happened; this should succeed
    if require_wake_word:
        tts.say(f"I'm listening for the word '{wake_word}'. Say '{wake_word}, help' to hear what I can do.",
                block=True)
    else:
        tts.say("I'm listening. Say 'help' to hear what I can do, or 'exit' to quit.", block=True)

    while True:
        try:
            text = recognizer.listen_once()
        except SpeechError as exc:
            logger.debug("Listen failed: %s", exc)
            continue
        except KeyboardInterrupt:
            break

        print(f"you> {text}")

        if require_wake_word:
            matched, remainder = strip_wake_word(text, wake_word)
            if not matched:
                logger.debug("Ignored utterance (no wake word): %s", text)
                continue
            if not remainder:
                tts.say("Yes? I'm listening.", block=True)
                try:
                    remainder = recognizer.listen_once()
                    print(f"you> {remainder}")
                except SpeechError:
                    continue
            command_text = remainder
        else:
            command_text = text

        if router.is_exit_command(command_text):
            tts.say("Goodbye!", block=True)
            break

        response = router.handle(command_text)
        tts.say(response)


def main():
    args = parse_args()

    tts = build_tts(rate=args.rate, disabled=args.no_speak)

    def announce_reminder(reminder):
        tts.say(f"Reminder: {reminder.text}")

    reminder_manager = ReminderManager(on_due=announce_reminder)
    reminder_manager.start()

    ctx = IntentContext(
        reminder_manager=reminder_manager,
        default_location=args.location,
        units=args.units,
    )
    router = IntentRouter(ctx)

    require_wake_word = not args.no_wake_word

    try:
        if args.text:
            run_text_mode(router, tts)
        else:
            from modules.speech_io import probe_hardware
            if probe_hardware(tts_rate=args.rate):
                run_voice_mode(router, tts, wake_word=args.wake_word, require_wake_word=require_wake_word)
            else:
                print("No working microphone/speakers detected. Falling back to text mode.\n")
                run_text_mode(router, tts)
    finally:
        reminder_manager.stop()
        tts.shutdown()


if __name__ == "__main__":
    sys.exit(main())
