"""
news.py
-------
Fetches top headlines from NewsAPI.org. Requires NEWSAPI_KEY to be set (see
modules/config.py). Get a free key at https://newsapi.org.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

from . import config

logger = logging.getLogger("assistant.news")

TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
EVERYTHING_URL = "https://newsapi.org/v2/everything"
REQUEST_TIMEOUT_SECONDS = 8

VALID_CATEGORIES = {"business", "entertainment", "general", "health", "science", "sports", "technology"}


class NewsError(Exception):
    """Raised when headlines can't be fetched."""


@dataclass
class Headline:
    title: str
    source: Optional[str] = None
    summary: Optional[str] = None
    link: Optional[str] = None


def get_headlines(category: str = "general", limit: int = 5,
                   country: Optional[str] = None, query: Optional[str] = None) -> List[Headline]:
    """
    Get top headlines. `category` should be one of VALID_CATEGORIES (falls
    back to "general" otherwise). If `query` is given, searches across all
    articles for that keyword instead of browsing top headlines by category.
    """
    try:
        api_key = config.require_newsapi_key()
    except RuntimeError as exc:
        raise NewsError(str(exc)) from exc

    if query:
        params = {"apiKey": api_key, "q": query, "pageSize": limit, "sortBy": "publishedAt", "language": "en"}
        url = EVERYTHING_URL
    else:
        cat = category.strip().lower() if category else "general"
        if cat not in VALID_CATEGORIES:
            cat = "general"
        params = {
            "apiKey": api_key,
            "pageSize": limit,
            "category": cat,
            "country": country or config.NEWS_COUNTRY,
        }
        url = TOP_HEADLINES_URL

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise NewsError(f"Could not reach NewsAPI: {exc}") from exc

    if response.status_code == 401:
        raise NewsError("The NewsAPI key is invalid.")

    try:
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise NewsError(f"NewsAPI returned an error: {exc}") from exc
    except ValueError as exc:
        raise NewsError("NewsAPI returned an unreadable response.") from exc

    if data.get("status") != "ok":
        raise NewsError(f"NewsAPI error: {data.get('message', 'unknown error')}")

    articles = data.get("articles", [])[:limit]
    if not articles:
        raise NewsError("No headlines found for that request.")

    return [
        Headline(
            title=a.get("title", "Untitled"),
            source=(a.get("source") or {}).get("name"),
            summary=a.get("description"),
            link=a.get("url"),
        )
        for a in articles
    ]


def spoken_headlines(headlines: List[Headline]) -> str:
    if not headlines:
        return "I couldn't find any news right now."
    lines = [f"Here are the top {len(headlines)} headlines."]
    for i, h in enumerate(headlines, start=1):
        source_note = f", from {h.source}" if h.source else ""
        lines.append(f"{i}. {h.title}{source_note}.")
    return " ".join(lines)
