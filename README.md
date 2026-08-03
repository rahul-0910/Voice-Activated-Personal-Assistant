# Personal Voice Assistant

A wake-word-activated personal assistant that can:
- **Check the weather** for any city (via [OpenWeatherMap](https://openweathermap.org/api))
- **Read the news** by category or keyword (via [NewsAPI](https://newsapi.org))
- **Set, list, and cancel reminders**, understanding natural phrases like "in 20 minutes" or "at 5 PM", and speaking them aloud when they're due

It listens for a wake word (default: **"assistant"**) before acting on a command, uses your microphone via `SpeechRecognition`, and speaks back with `pyttsx3` (offline TTS). If no microphone or audio output device is found, it **automatically falls back to a typed-text prompt** — no flag required, no crash.

## Project layout

```
voice_assistant/
├── assistant.py             # main loop: wake word + intent routing
├── requirements.txt
└── modules/
    ├── config.py             # API keys & settings from environment variables
    ├── speech_io.py           # mic input (SpeechRecognition) + TTS (pyttsx3), hardware probing
    ├── weather.py             # OpenWeatherMap integration
    ├── news.py                # NewsAPI integration
    ├── reminders.py           # natural-language time parsing, JSON persistence, background alerts
    └── intents.py             # regex-based router: recognized text -> feature handlers
```

## Setup

1. **Python 3.9+** required.

2. **System audio dependencies** (for `PyAudio` / mic access, and `pyttsx3` / TTS output):

   - macOS: `brew install portaudio`
   - Ubuntu/Debian: `sudo apt-get install portaudio19-dev python3-pyaudio espeak-ng`
   - Windows: usually works out of the box with `pip install pyaudio pyttsx3`

3. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **API keys** — both are free tiers:

   - OpenWeatherMap: sign up at https://openweathermap.org/api, grab your key
   - NewsAPI: sign up at https://newsapi.org, grab your key

   Set them as environment variables, or create a `.env` file next to `assistant.py`:

   ```bash
   # .env
   OPENWEATHER_API_KEY=your_openweathermap_key
   NEWSAPI_KEY=your_newsapi_key

   # optional overrides
   ASSISTANT_WAKE_WORD=assistant
   ASSISTANT_DEFAULT_LOCATION=Jaipur
   ASSISTANT_UNITS=metric
   ASSISTANT_NEWS_COUNTRY=us
   ASSISTANT_REQUIRE_WAKE_WORD=true
   ```

   Without `python-dotenv` installed, just export these as real environment variables instead — everything still works.

## Running it

```bash
python assistant.py                  # voice mode if hardware is available, else auto text-mode
python assistant.py --text           # force typed text mode
python assistant.py --no-wake-word   # skip the wake word, act on every utterance
python assistant.py --wake-word "computer"
python assistant.py --location "New York" --units imperial
python assistant.py --no-speak       # print responses instead of speaking (still listens by voice)
```

## Example commands

With the wake word (default "assistant"), say things like:

- "Assistant, what's the weather in Tokyo?"
- "Assistant, what's the weather like?" (uses your default location)
- "Hey assistant, give me the technology news"
- "Assistant, remind me to call mom in 20 minutes"
- "Assistant, remind me to take the medicine at 8 AM"
- "Assistant, list my reminders"
- "Assistant, cancel reminder a1b2c3d4"
- "Assistant, help"
- "Assistant, exit"

If you just say "Assistant" by itself, it responds "Yes? I'm listening." and waits for your next sentence — no need to repeat the wake word.

In `--text` mode, the wake word isn't needed; just type the command directly.

## How it works

- **`modules/speech_io.py`** wraps `SpeechRecognition` (mic capture + Google's free recognition endpoint) and `pyttsx3` (offline TTS). Both `TextToSpeech` and `SpeechRecognizer` probe their hardware at construction time and raise `HardwareUnavailableError` if nothing usable is found. `assistant.py` calls `probe_hardware()` up front and drops to typed text automatically if voice I/O isn't available — it never just crashes on a headless machine.
- **`assistant.py`** runs the main loop: continuously listens, checks each utterance for the wake word (`strip_wake_word()`, case-insensitive, handles "hey assistant ..." too), strips it off, and only then routes the remainder to the intent router.
- **`modules/weather.py`** calls the OpenWeatherMap current-weather endpoint and builds a short spoken sentence, including a "feels like" callout and a humidity warning when relevant. Clear error messages for bad city names (404) and bad API keys (401).
- **`modules/news.py`** pulls top headlines from NewsAPI by category (`business`, `technology`, `science`, `sports`, etc.), or does a keyword search across all articles if you ask about a specific topic.
- **`modules/reminders.py`** parses times with `dateparser` (falls back to a simple "in N minutes/hours" parser if `dateparser` isn't installed), stores reminders in `~/.voice_assistant/reminders.json`, and runs a background thread that polls every 15 seconds (configurable via `ASSISTANT_REMINDER_POLL_SECONDS`) and fires a callback — hooked to TTS in `assistant.py` — exactly once per reminder.
- **`modules/intents.py`** is a small regex-based intent router — no heavy NLU dependency. Each rule is a `(pattern, handler)` pair; add your own via `router.register(pattern, handler)`.
- **`modules/config.py`** centralizes every environment-variable read (API keys, wake word, default location/units, TTS rate, poll interval) so nothing else in the codebase touches `os.environ` directly.

## Extending it

- **Swap the speech engines:** replace `recognize_google` in `speech_io.py` with an offline engine like Vosk or `openai-whisper` for privacy or offline use.
- **Better wake-word detection:** the current approach checks the start of each transcribed utterance. For lower latency and less API usage, swap in a dedicated wake-word engine like Picovoice Porcupine, which runs locally and only transcribes speech after the wake word is detected.
- **Add new skills:** write a new module (e.g. `calendar.py`), then register a pattern + handler in `IntentRouter._register_builtin_intents()`.
- **Cache weather/news lookups** with a simple TTL cache if you want to reduce API calls during repeated queries.

## Notes & limitations

- Voice recognition uses Google's free web API by default, which requires internet and has no official uptime/rate-limit guarantee — fine for personal use, not for production.
- The intent router is intentionally simple (keyword/regex based) rather than a full NLU model, so it won't catch every possible phrasing, but it's easy to read and extend.
- Both OpenWeatherMap and NewsAPI free tiers have rate limits (typically 1,000 calls/day and 100 requests/day respectively at time of writing) — check current limits on their sites if you hit errors.
- On Linux, `pyttsx3` needs `espeak-ng` installed system-wide; without it, `TextToSpeech` will raise `HardwareUnavailableError` and the app will fall back to printed text, which is exactly what happened during testing in this sandboxed environment.
