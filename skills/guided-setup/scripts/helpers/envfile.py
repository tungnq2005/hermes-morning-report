"""Shared helpers for guided-setup: ~/.hermes/.env I/O and pasted-value hygiene.

Every key in this flow arrives by chat, typed or pasted by a non-technical user on a
phone. What lands in the message is rarely the bare key: it comes wrapped in quotes,
prefixed with "API key:", split across lines by Telegram, or copied together with the
surrounding sentence. Cleaning that up here -- once, in one place -- is what keeps the
rest of the flow from writing a broken value into .env and failing an hour later.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Placeholders people paste when they think they are pasting a key.
PLACEHOLDERS = {
    "x", "xx", "xxx", "xxxx", "your_key", "your-key", "yourkey", "api_key", "apikey",
    "key", "none", "null", "todo", "changeme", "<key>", "paste_here", "dán_key_vào_đây",
}

_LABEL_RE = re.compile(r"^[\w\s\-\.()/]{0,40}?[:=]\s*(\S.*)$")


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def env_path() -> Path:
    return hermes_home() / ".env"


def read_env(path: Path | None = None) -> dict[str, str]:
    """Parse ~/.hermes/.env into a dict. Missing or unreadable file -> empty dict."""
    path = path or env_path()
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def set_env(key: str, value: str, path: Path | None = None) -> Path:
    """Write KEY=value into .env, updating in place if present. Keeps the file at 0600."""
    path = path or env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    os.chmod(path, 0o600)

    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[index] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def mask(value: str) -> str:
    """Short fingerprint of a secret -- enough for the user to recognise it, never enough to use it."""
    if not value:
        return ""
    if len(value) <= 8:
        return f"{value[:2]}…({len(value)} chars)"
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)"


def clean_pasted(raw: str) -> tuple[str, list[str]]:
    """Turn a chat message into the key it contains. Returns (value, problems).

    Problems are advisory: the caller decides whether to refuse or just warn. An empty
    returned value always means "nothing usable in this message".
    """
    problems: list[str] = []
    text = (raw or "").replace("​", "").strip()  # zero-width space, common in phone copies
    text = text.strip("`")  # Telegram/markdown code formatting
    if not text:
        return "", ["empty"]

    # Telegram wraps long pastes; the key is almost always the last non-empty line.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    value = lines[-1] if lines else ""

    # "API key: abc123" / "EXA_API_KEY=abc123" -> abc123
    label_match = _LABEL_RE.match(value)
    if label_match and not value.lower().startswith(("http://", "https://")):
        value = label_match.group(1).strip()

    value = value.strip().strip("`").strip("\"'").rstrip(".,;")
    value = value.strip()

    if not value:
        return "", ["empty"]
    if value.lower() in PLACEHOLDERS or value.startswith("<") and value.endswith(">"):
        problems.append("placeholder")
    if value.lower().startswith(("http://", "https://")):
        problems.append("looks_like_url")
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        problems.append("looks_like_email")
    if re.search(r"\s", value):
        problems.append("contains_spaces")
    if len(value) < 8 and "placeholder" not in problems:
        problems.append("too_short")
    return value, problems
