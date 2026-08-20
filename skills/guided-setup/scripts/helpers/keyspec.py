"""What each key is, who needs it, where the user gets it, and how to prove it works.

One registry, used by both check_setup.py and save_key.py, so the status report and the
save path can never disagree about which keys matter.

`required` is deliberately narrow. Morning Report needs SOMETHING to search with -- Exa
or Brave -- and everything else degrades instead of failing: without Firecrawl the
collector falls back to plain HTTP fetching, and without Google doc-convert renders
locally. Marking those "required" would block a user who is perfectly able to start.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 20

KEY_SPECS: dict[str, dict] = {
    "exa": {
        "env": "EXA_API_KEY",
        "label_en": "Exa (news search)",
        "label_vi": "Exa (tìm tin)",
        "used_by": ["morning-report"],
        "tier": "primary",  # primary | fallback | optional
        "console": "https://dashboard.exa.ai/api-keys",
        "prefix_hint": None,
        "guide_anchor": "exa",
    },
    "firecrawl": {
        "env": "FIRECRAWL_API_KEY",
        "label_en": "Firecrawl (article reader)",
        "label_vi": "Firecrawl (đọc nội dung bài báo)",
        "used_by": ["morning-report"],
        "tier": "optional",
        "console": "https://www.firecrawl.dev/app/api-keys",
        "prefix_hint": "fc-",
        "guide_anchor": "firecrawl",
    },
    "brave": {
        "env": "BRAVE_SEARCH_API_KEY",
        "label_en": "Brave Search (search fallback)",
        "label_vi": "Brave Search (tìm tin dự phòng)",
        "used_by": ["morning-report"],
        "tier": "fallback",
        "console": "https://api-dashboard.search.brave.com/app/keys",
        "prefix_hint": "BSA",
        "guide_anchor": "brave",
    },
}

# Accept an env var name as the key id too, so the agent can pass either form.
ENV_TO_ID = {spec["env"]: key_id for key_id, spec in KEY_SPECS.items()}


def resolve_id(name: str) -> str | None:
    """Map 'exa', 'EXA_API_KEY', or 'exa_api_key' to the registry id."""
    candidate = (name or "").strip()
    if candidate.upper() in ENV_TO_ID:
        return ENV_TO_ID[candidate.upper()]
    return candidate.lower() if candidate.lower() in KEY_SPECS else None


def _http(request: urllib.request.Request) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read(2000).decode("utf-8", "replace")


def _verdict(status: int, ok_codes: tuple[int, ...]) -> dict:
    """Only an explicit auth rejection means 'bad key'.

    A timeout, a 5xx or a blocked outbound connection says something about the network,
    not about the key -- calling that "invalid" would send the user back to the console
    to regenerate a key that was fine.
    """
    if status in ok_codes:
        return {"ok": True, "state": "verified", "http_status": status}
    if status in (401, 403):
        return {"ok": False, "state": "rejected", "http_status": status}
    return {"ok": False, "state": "unverified", "http_status": status}


def verify_exa(value: str) -> dict:
    payload = json.dumps({"query": "test", "numResults": 1, "type": "fast"}).encode()
    request = urllib.request.Request(
        "https://api.exa.ai/search", data=payload,
        headers={"Content-Type": "application/json", "x-api-key": value})
    status, _ = _http(request)
    return _verdict(status, (200,))


def verify_firecrawl(value: str) -> dict:
    request = urllib.request.Request(
        "https://api.firecrawl.dev/v1/team/credit-usage",
        headers={"Authorization": f"Bearer {value}"})
    status, _ = _http(request)
    return _verdict(status, (200,))


def verify_brave(value: str) -> dict:
    params = urllib.parse.urlencode({"q": "test", "count": 1})
    request = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={"Accept": "application/json", "X-Subscription-Token": value})
    status, _ = _http(request)
    # 429 is the free plan's one-request-per-second limit answering, which only a valid
    # key gets to hear.
    return _verdict(status, (200, 429))


VERIFIERS = {"exa": verify_exa, "firecrawl": verify_firecrawl, "brave": verify_brave}


def verify(key_id: str, value: str) -> dict:
    verifier = VERIFIERS.get(key_id)
    if not verifier:
        return {"ok": False, "state": "no_verifier", "http_status": 0}
    try:
        return verifier(value)
    except Exception as err:  # noqa: BLE001 - a network probe must not crash setup
        return {"ok": False, "state": "unverified", "http_status": 0, "error": str(err)[:200]}
