#!/usr/bin/env python3
"""Google TTS language support helpers for Morning Report audio."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

# Data
LANGUAGE_DATA_PATH = Path(__file__).with_name("google-tts-languages.json")
TTS_DATA = json.loads(LANGUAGE_DATA_PATH.read_text(encoding="utf-8"))
TTS_LANGUAGES = TTS_DATA["languages"]
LANGUAGE_ALIASES = TTS_DATA["aliases"]

# Google TTS probe
GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


# Public helpers
def check_tts_language(language: str | None) -> dict[str, str | None]:
    clean = (language or "").strip()
    if clean in TTS_LANGUAGES:
        return {"lang": clean}
    return {"lang": LANGUAGE_ALIASES.get(clean.lower()) if clean else None}


def test_google_tts_language(language: str | None, timeout: int = 10) -> dict[str, bool]:
    lang = check_tts_language(language)["lang"]
    if not lang:
        return {"success": False}

    params = urllib.parse.urlencode(
        {
            "ie": "UTF-8",
            "client": "tw-ob",
            "tl": lang,
            "q": TTS_LANGUAGES[lang]["test_text"],
        }
    )
    request = urllib.request.Request(
        f"{GOOGLE_TTS_URL}?{params}",
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(512)
        return {"success": len(data) > 128}
    except Exception:
        return {"success": False}
