"""
intents.py
----------
Small regex/keyword-based intent router. Takes recognized text (already
stripped of the wake word by assistant.py) and dispatches to the right
feature module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, List, Tuple

from . import config
from . import news as news_module
from . import weather as weather_module
from .reminders import ReminderError, ReminderManager

logger = logging.getLogger("assistant.intents")

EXIT_WORDS = {"exit", "quit", "stop", "goodbye", "bye", "shut down"}


@dataclass
class IntentContext:
    reminder_manager: ReminderManager
    default_location: str = config.DEFAULT_LOCATION
    units: str = config.UNITS


class IntentRouter:
    """
    Holds an ordered list of (pattern, handler) rules. The first pattern
    that matches the utterance wins. Add new commands with `register()`.
    """

    def __init__(self, ctx: IntentContext):
        self.ctx = ctx
        self._rules: List[Tuple[re.Pattern, Callable[[re.Match, IntentContext], str]]] = []
        self._register_builtin_intents()

    def register(self, pattern: str, handler: Callable[[re.Match, IntentContext], str], flags=re.IGNORECASE):
        self._rules.append((re.compile(pattern, flags), handler))

    def is_exit_command(self, text: str) -> bool:
        return text.strip().lower() in EXIT_WORDS

    def handle(self, text: str) -> str:
        """Return the spoken response for a piece of recognized text (wake word already stripped)."""
        text = text.strip()
        if not text:
            return "I didn't catch that. Could you repeat it?"

        for pattern, handler in self._rules:
            match = pattern.search(text)
            if match:
                try:
                    return handler(match, self.ctx)
                except Exception:  # noqa: BLE001
                    logger.exception("Handler failed for input: %s", text)
                    return "Something went wrong while handling that. Please try again."

        return (
            "I'm not sure how to help with that yet. You can ask me about the "
            "weather, the news, or say 'remind me to ... in ...'."
        )

    # -- built-in intents -----------------------------------------------

    def _register_builtin_intents(self):
        self.register(
            r"weather(?:\s+(?:like\s+)?in\s+(?P<location>[\w\s,]+))?",
            self._handle_weather,
        )
        self.register(
            r"(news|headlines)(?:\s+(?:about|on|for)\s+(?P<category>\w+))?",
            self._handle_news,
        )
        self.register(
            r"remind me to (?P<text>.+?) (?P<when>(?:in|at|on|tomorrow|tonight).+)$",
            self._handle_add_reminder,
        )
        self.register(
            r"(list|what are|show).*(reminders|to-?do)",
            self._handle_list_reminders,
        )
        self.register(
            r"cancel reminder (?P<id>\w+)",
            self._handle_cancel_reminder,
        )
        self.register(r"^help$|what can you do", self._handle_help)

    @staticmethod
    def _handle_weather(match: re.Match, ctx: IntentContext) -> str:
        location = (match.group("location") or ctx.default_location).strip()
        try:
            report = weather_module.get_weather(location, units=ctx.units)
        except weather_module.WeatherError as exc:
            return f"Sorry, I couldn't get the weather for {location}: {exc}"
        return report.spoken_summary()

    @staticmethod
    def _handle_news(match: re.Match, ctx: IntentContext) -> str:
        category = match.group("category") or "general"
        try:
            headlines = news_module.get_headlines(category=category, limit=5)
        except news_module.NewsError as exc:
            return f"Sorry, I couldn't fetch the news: {exc}"
        return news_module.spoken_headlines(headlines)

    @staticmethod
    def _handle_add_reminder(match: re.Match, ctx: IntentContext) -> str:
        text = match.group("text").strip()
        when_text = match.group("when").strip()
        try:
            reminder = ctx.reminder_manager.add(text, when_text)
        except ReminderError as exc:
            return f"Sorry, I couldn't set that reminder: {exc}"
        due = reminder.due_datetime().strftime("%A %I:%M %p")
        return f"Got it. I'll remind you to {text} on {due}. Reminder ID {reminder.id}."

    @staticmethod
    def _handle_list_reminders(match: re.Match, ctx: IntentContext) -> str:
        upcoming = ctx.reminder_manager.list_upcoming()
        if not upcoming:
            return "You have no upcoming reminders."
        lines = ["Here are your upcoming reminders."]
        for r in upcoming:
            due = r.due_datetime().strftime("%A %I:%M %p")
            lines.append(f"{r.text}, due {due}, ID {r.id}.")
        return " ".join(lines)

    @staticmethod
    def _handle_cancel_reminder(match: re.Match, ctx: IntentContext) -> str:
        reminder_id = match.group("id")
        found = ctx.reminder_manager.cancel(reminder_id)
        return f"Reminder {reminder_id} cancelled." if found else f"I couldn't find a reminder with ID {reminder_id}."

    @staticmethod
    def _handle_help(match: re.Match, ctx: IntentContext) -> str:
        return (
            "I can check the weather, for example 'what's the weather in Tokyo'. "
            "I can read the news, for example 'give me the technology news'. "
            "I can set reminders, for example 'remind me to call mom in 20 minutes'. "
            "I can list reminders with 'list my reminders', or cancel one with "
            "'cancel reminder' followed by its ID. Say 'exit' any time to quit."
        )
