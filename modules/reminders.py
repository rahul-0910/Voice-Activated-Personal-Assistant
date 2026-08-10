"""
reminders.py
------------
Set, list, and get notified about reminders.

Reminders are persisted to a JSON file so they survive restarts. A background
thread wakes up periodically, and whenever a reminder's due time has passed
it fires a callback (typically hooked up to TTS) exactly once.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from . import config

logger = logging.getLogger("assistant.reminders")

DEFAULT_STORE_PATH = Path.home() / ".voice_assistant" / "reminders.json"


class ReminderError(Exception):
    """Raised when a reminder can't be created or parsed."""


@dataclass
class Reminder:
    id: str
    text: str
    due_at: str  # ISO 8601 timestamp
    created_at: str
    fired: bool = False

    def due_datetime(self) -> datetime:
        return datetime.fromisoformat(self.due_at)


class ReminderStore:
    """Handles reading/writing reminders.json. Callers should go through
    ReminderManager, which serializes access via a lock."""

    def __init__(self, path: Path = DEFAULT_STORE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _write(self, reminders: List[Reminder]):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in reminders], f, indent=2)

    def load(self) -> List[Reminder]:
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [Reminder(**r) for r in raw]

    def save(self, reminders: List[Reminder]):
        self._write(reminders)


def parse_when(when_text: str, now: Optional[datetime] = None) -> datetime:
    """
    Parse a natural-language time expression ("in 20 minutes", "at 5 PM",
    "tomorrow at 8am") into a concrete datetime. Tries `dateparser` first;
    falls back to a simple "in N minutes/hours/seconds" parser if
    dateparser isn't installed.
    """
    now = now or datetime.now()

    try:
        import dateparser

        settings = {"PREFER_DATES_FROM": "future", "RELATIVE_BASE": now}
        result = dateparser.parse(when_text, settings=settings)
        if result:
            return result
    except ImportError:
        logger.warning("dateparser not installed; falling back to simple parsing.")

    tokens = when_text.lower().split()
    if len(tokens) >= 3 and tokens[0] == "in" and tokens[1].isdigit():
        amount = int(tokens[1])
        unit = tokens[2].rstrip("s")
        if unit == "minute":
            return now + timedelta(minutes=amount)
        if unit == "hour":
            return now + timedelta(hours=amount)
        if unit == "second":
            return now + timedelta(seconds=amount)

    raise ReminderError(
        f"Could not understand the time '{when_text}'. Try something like "
        "'in 10 minutes' or 'at 5 PM'."
    )


class ReminderManager:
    """Owns the reminder list plus a background polling thread. Instantiate
    once and share it across the app."""

    def __init__(self, store: Optional[ReminderStore] = None,
                 on_due: Optional[Callable[[Reminder], None]] = None,
                 poll_interval: Optional[float] = None):
        self._store = store or ReminderStore()
        self._lock = threading.Lock()
        self._on_due = on_due
        self._poll_interval = poll_interval or config.REMINDER_POLL_INTERVAL_SECONDS
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- CRUD -------------------------------------------------------------

    def add(self, text: str, when_text: str) -> Reminder:
        due_at = parse_when(when_text)
        reminder = Reminder(
            id=str(uuid.uuid4())[:8],
            text=text.strip(),
            due_at=due_at.isoformat(),
            created_at=datetime.now().isoformat(),
        )
        with self._lock:
            reminders = self._store.load()
            reminders.append(reminder)
            self._store.save(reminders)
        logger.info("Added reminder %s due at %s", reminder.id, reminder.due_at)
        return reminder

    def list_upcoming(self) -> List[Reminder]:
        with self._lock:
            reminders = self._store.load()
        upcoming = [r for r in reminders if not r.fired]
        return sorted(upcoming, key=lambda r: r.due_datetime())

    def cancel(self, reminder_id: str) -> bool:
        with self._lock:
            reminders = self._store.load()
            remaining = [r for r in reminders if r.id != reminder_id]
            found = len(remaining) != len(reminders)
            if found:
                self._store.save(remaining)
        return found

    # -- Background polling ------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Reminder polling thread started (interval=%ss).", self._poll_interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._check_due()
            self._stop_event.wait(self._poll_interval)

    def _check_due(self):
        now = datetime.now()
        with self._lock:
            reminders = self._store.load()
            due_now = [r for r in reminders if not r.fired and r.due_datetime() <= now]
            if due_now:
                for r in reminders:
                    if r in due_now:
                        r.fired = True
                self._store.save(reminders)

        for reminder in due_now:
            logger.info("Reminder due: %s", reminder.text)
            if self._on_due:
                try:
                    self._on_due(reminder)
                except Exception:  # noqa: BLE001
                    logger.exception("on_due callback failed for reminder %s", reminder.id)
