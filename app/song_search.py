"""Proxy de recherche de morceaux via l'iTunes Search API (autocomplétion questionnaire.html)."""
import json
import logging
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 3
MAX_RESULTS = 5
CACHE_TTL_SECONDS = 3600
_REQUEST_TIMEOUT = 3.0

_cache: dict[str, tuple[float, list[str]]] = {}


def search_songs(query: str) -> list[str]:
    """Retourne jusqu'à MAX_RESULTS suggestions "Titre — Artiste"."""
    query = (query or "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []

    cache_key = query.lower()
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    params = {
        "term": query,
        "media": "music",
        "entity": "song",
        "limit": str(MAX_RESULTS),
    }
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=_REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = [
            f"{item['trackName']} — {item['artistName']}"
            for item in data.get("results", [])
            if item.get("trackName") and item.get("artistName")
        ]
    except Exception as e:
        logger.warning(f"Recherche iTunes échouée pour '{query}' : {e}")
        return []

    _cache[cache_key] = (time.time(), results)
    return results
