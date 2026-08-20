"""Google OAuth without a terminal, a browser on the server, or an SSH tunnel.

authorize_google.py runs a real loopback server on the VPS, which forces whoever is
installing to open `ssh -L 8765:localhost:8765` from their laptop before clicking
Allow. That is a reasonable ask for an operator and an impossible one for the person
this flow is written for -- they are holding a phone with Telegram open.

The way out is that a Desktop OAuth client redirects to http://localhost:<port>, and
nothing has to be listening there. The user taps Allow, their browser fails to load the
loopback address, and the address bar is left holding the whole redirect URL --
authorization code included. They copy that URL into the chat and we finish the
exchange server-side. Two messages, no tunnel.

The PKCE verifier has to survive between the two chat turns (two separate processes),
so `start` writes it to oauth-pending.json next to the credentials and `finish` reads
it back.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRIVE_ABOUT = "https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)"

SCOPE_DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"
SCOPE_DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
SCOPE_SETS = {
    "minimal": [SCOPE_DRIVE_FILE],
    "private-links": [SCOPE_DRIVE_FILE, SCOPE_DRIVE_READONLY],
}
# The chat flow defaults to minimal on purpose: drive.file is non-sensitive, so the user
# never meets the "Google hasn't verified this app" screen -- the single most common
# place a non-technical user abandons the setup.
DEFAULT_SCOPE_SET = "minimal"

PENDING_FILE = "oauth-pending.json"
PENDING_TTL_SECONDS = 3600
DEFAULT_PORT = 8765

_CODE_RE = re.compile(r"[?&]code=([^&\s]+)")
_STATE_RE = re.compile(r"[?&]state=([^&\s]+)")
_ERROR_RE = re.compile(r"[?&]error=([^&\s]+)")


class GoogleSetupError(Exception):
    """Anything the user can fix, phrased so the agent can relay it as-is."""


# -- credentials directory ----------------------------------------------
def doc_convert_default_creds_dir() -> Path:
    """Where google_io.py looks when DOC_CONVERT_GCREDS_DIR is not exported."""
    here = Path(__file__).resolve()
    # <root>/skills/guided-setup/scripts/helpers/ -> <root>/skills/doc-convert/state/google-creds
    skills_dir = here.parent.parent.parent.parent
    return skills_dir / "doc-convert" / "state" / "google-creds"


def resolve_creds_dir(explicit: str | None = None, env_file_value: str | None = None) -> Path:
    """Pick the directory doc-convert will actually read at runtime.

    The process environment wins over ~/.hermes/.env, because google_io.py reads
    os.environ and nothing else: a path that only exists in .env is a path doc-convert
    cannot see. A value found only in .env is used when it already holds credentials
    (an install done the terminal way), and the caller is told about the mismatch.
    """
    if explicit:
        return Path(explicit).expanduser()
    from_env = os.environ.get("DOC_CONVERT_GCREDS_DIR")
    if from_env:
        return Path(from_env).expanduser()
    if env_file_value:
        candidate = Path(env_file_value).expanduser()
        if (candidate / "client_secret.json").exists() or (candidate / "token.json").exists():
            return candidate
    return doc_convert_default_creds_dir()


def link_into_default(creds_dir: Path) -> str:
    """Make the credentials reachable at google_io's default path too.

    doc-convert only sees DOC_CONVERT_GCREDS_DIR if the gateway exports ~/.hermes/.env
    into tool processes, which is not guaranteed. A symlink at the default path removes
    that dependency: whichever way google_io resolves, it lands on the same files.
    """
    default = doc_convert_default_creds_dir()
    creds_dir = Path(creds_dir).resolve()
    if default.exists() and not default.is_symlink():
        if default.resolve() == creds_dir:
            return "already_default"
        # A real directory holding real credentials is not ours to replace.
        if any(default.iterdir()):
            return "default_dir_not_empty"
        default.rmdir()
    elif default.is_symlink():
        if default.resolve() == creds_dir:
            return "already_linked"
        default.unlink()
    default.parent.mkdir(parents=True, exist_ok=True)
    try:
        default.symlink_to(creds_dir, target_is_directory=True)
    except OSError as err:
        return f"link_failed:{err}"
    return "linked"


# -- client_secret.json -------------------------------------------------
def parse_client_json(raw: str) -> dict:
    """Validate a pasted client_secret.json and return its parsed form.

    A Web-application client is the classic wrong turn here: it looks identical in the
    download dialog and only fails much later with redirect_uri_mismatch, by which time
    nobody remembers which dropdown caused it. Desktop clients carry the "installed"
    key, so the mistake is caught while the console tab is still open.
    """
    text = (raw or "").strip().strip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise GoogleSetupError("no_json_found")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as err:
        raise GoogleSetupError(f"invalid_json:{err.msg}") from err
    if "web" in data:
        raise GoogleSetupError("wrong_client_type:web")
    if "installed" not in data:
        raise GoogleSetupError("wrong_client_type:unknown")
    section = data["installed"]
    if not section.get("client_id") or not section.get("client_secret"):
        raise GoogleSetupError("missing_client_fields")
    return data


def client_json_from_pair(client_id: str, client_secret: str) -> dict:
    """Build a Desktop-client file from an ID and secret read off the console screen.

    Downloading the JSON on a phone and forwarding it into Telegram is more steps than
    copying two strings, so both routes are supported.
    """
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise GoogleSetupError("bad_client_id")
    if not client_secret:
        raise GoogleSetupError("missing_client_fields")
    return {"installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": AUTH_ENDPOINT,
        "token_uri": TOKEN_ENDPOINT,
        "redirect_uris": ["http://localhost"],
    }}


def write_client_json(creds_dir: Path, data: dict) -> Path:
    creds_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(creds_dir, 0o700)
    path = creds_dir / "client_secret.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def read_client_json(creds_dir: Path) -> dict:
    path = Path(creds_dir) / "client_secret.json"
    if not path.exists():
        raise GoogleSetupError("no_client_secret")
    return parse_client_json(path.read_text(encoding="utf-8"))


# -- the two-message consent flow ---------------------------------------
def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def scope_list(scope_set: str) -> list[str]:
    return SCOPE_SETS.get(scope_set, SCOPE_SETS[DEFAULT_SCOPE_SET])


def build_auth_url(creds_dir: Path, scope_set: str = DEFAULT_SCOPE_SET,
                   port: int = DEFAULT_PORT) -> dict:
    """Return the consent URL and remember what `finish` will need to verify it."""
    creds_dir = Path(creds_dir)
    client = read_client_json(creds_dir)["installed"]
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{port}"
    scopes = scope_list(scope_set)
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        # offline + consent is what makes Google hand back a refresh token; without it
        # the bot works until the first access token expires an hour later.
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    pending = {
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "scope_set": scope_set,
        "scopes": scopes,
        "created_at": int(time.time()),
    }
    creds_dir.mkdir(parents=True, exist_ok=True)
    path = creds_dir / PENDING_FILE
    path.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)
    return {
        "auth_url": f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}",
        "redirect_uri": redirect_uri,
        "scope_set": scope_set,
        "scopes": scopes,
    }


def read_pending(creds_dir: Path) -> dict:
    path = Path(creds_dir) / PENDING_FILE
    if not path.exists():
        raise GoogleSetupError("no_pending_authorization")
    pending = json.loads(path.read_text(encoding="utf-8"))
    if int(time.time()) - int(pending.get("created_at", 0)) > PENDING_TTL_SECONDS:
        raise GoogleSetupError("authorization_expired")
    return pending


def extract_code(pasted: str) -> tuple[str, str]:
    """Pull (code, state) out of whatever the user copied from the address bar."""
    text = (pasted or "").strip().strip("`").strip()
    error = _ERROR_RE.search(text)
    if error:
        raise GoogleSetupError(f"consent_error:{urllib.parse.unquote(error.group(1))}")
    match = _CODE_RE.search(text)
    if match:
        code = urllib.parse.unquote(match.group(1))
        state_match = _STATE_RE.search(text)
        return code, urllib.parse.unquote(state_match.group(1)) if state_match else ""
    # Some users paste only the code fragment; Google's codes start with "4/".
    if text.startswith("4/") and " " not in text:
        return text, ""
    raise GoogleSetupError("no_code_in_url")


def exchange_code(creds_dir: Path, code: str, pending: dict) -> dict:
    client = read_client_json(creds_dir)["installed"]
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": pending["redirect_uri"],
        "grant_type": "authorization_code",
        "code_verifier": pending["code_verifier"],
    }).encode()
    request = urllib.request.Request(
        TOKEN_ENDPOINT, data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as err:
        body = err.read(2000).decode("utf-8", "replace")
        try:
            detail = json.loads(body).get("error", "")
        except json.JSONDecodeError:
            detail = body[:200]
        raise GoogleSetupError(f"token_exchange_failed:{detail}") from err
    except Exception as err:  # noqa: BLE001 - network shape varies, the message is what matters
        raise GoogleSetupError(f"token_exchange_failed:{err}") from err

    if not data.get("refresh_token"):
        # Without a refresh token the bot dies at the first hourly expiry, so treat this
        # as a failed authorization rather than storing a token that expires today.
        raise GoogleSetupError("no_refresh_token")
    return data


def write_token(creds_dir: Path, token_data: dict, client: dict, scopes: list[str]) -> Path:
    """Store the token in the exact shape google.oauth2 Credentials reads back."""
    creds_dir = Path(creds_dir)
    expiry = None
    if token_data.get("expires_in"):
        expiry = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + int(token_data["expires_in"]))) + "Z"
    granted = (token_data.get("scope") or " ".join(scopes)).split()
    payload = {
        "token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "token_uri": TOKEN_ENDPOINT,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "scopes": granted,
        "universe_domain": "googleapis.com",
        "account": "",
    }
    if expiry:
        payload["expiry"] = expiry
    path = creds_dir / "token.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    (creds_dir / PENDING_FILE).unlink(missing_ok=True)
    return path


def token_scopes(creds_dir: Path) -> list[str]:
    """Scopes the stored token actually carries -- the only honest source."""
    path = Path(creds_dir) / "token.json"
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("scopes") or [])
    except (OSError, json.JSONDecodeError):
        return []


def whoami(access_token: str) -> str:
    """Which Google account the bot just got access to -- the one detail worth confirming.

    Files land in this account's Drive, and picking the wrong account on the consent
    screen is otherwise silent.
    """
    request = urllib.request.Request(
        DRIVE_ABOUT, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read())
        return str((data.get("user") or {}).get("emailAddress") or "")
    except Exception:  # noqa: BLE001 - about.get is a nicety, never a gate
        return ""
