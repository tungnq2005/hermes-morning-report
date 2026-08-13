"""Fetch openly-licensed slide imagery from Openverse. No API key required.

Anonymous callers get 20 requests/minute and 200/day, which is far more than one
deck needs. Every failure here is soft: a slide without a picture is fine, a slide
with the wrong picture is not.

Openverse indexes almost nothing under Vietnamese queries -- "Hạ tầng điện toán đám
mây" returns zero results and "Tổng quan kinh tế số" returns photographs of fishing
boats. Callers are therefore expected to pass English queries (the agent translates
the section titles). When no usable query exists we return no image rather than an
irrelevant one.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

API_URL = "https://api.openverse.org/v1/images/"

# cc0 and pdm need no credit; by needs attribution, which the credits slide renders.
# by-sa is excluded because share-alike would reach into the client's own deck, and
# the nc/nd variants would bar commercial use and cropping.
LICENSES = "cc0,pdm,by"

USER_AGENT = "openclaw-doc-convert/1.0"
SEARCH_TIMEOUT = 8
# Openverse hands back originals hosted on Flickr, which are slow enough that 12s
# timed out on a real run. Two tries at 20s each still bounds a stuck deck.
DOWNLOAD_TIMEOUT = 20
DOWNLOAD_ATTEMPTS = 2
MAX_IMAGE_BYTES = 4_000_000

# Openverse orders by its own relevance, which put a NASA belly-camera photo first for
# "cloud data center". Over-fetch and re-rank on how many query words the title carries.
OVER_FETCH = 5
# How many ranked hits `fetch` will try before leaving a slide bare.
CANDIDATES = 3

# Set to 1 to keep conversions (and the test suite) off the network.
DISABLE_ENV = "DOC_CONVERT_DISABLE_IMAGE_SEARCH"


class ImageSearchError(Exception):
    pass


class UnsupportedImageFormat(ImageSearchError):
    """The bytes are an image, but not one python-pptx can embed."""


# python-pptx embeds these and nothing else. Sniff the bytes rather than trusting the
# extension or Content-Type: rawpixel serves WebP from a URL ending in `.jpg`, which
# used to be saved as `slide-image-NN.jpg` and then silently rejected at embed time.
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tiff"),
    (b"MM\x00*", ".tiff"),
)


def image_ext(data: bytes) -> str | None:
    """Extension for embeddable bytes, or None when the format is unusable."""
    for magic, ext in _MAGIC:
        if data.startswith(magic):
            return ext
    return None


def disabled() -> bool:
    return os.environ.get(DISABLE_ENV, "").strip().lower() not in ("", "0", "false", "no")


def _get(url: str, timeout: int) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        content_type = (response.headers.get("Content-Type") or "").lower()
        return response.read(MAX_IMAGE_BYTES + 1), content_type


def relevance(title: str, query: str) -> int:
    """How many meaningful words of the query the title actually contains."""
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 3}
    if not words:
        return 0
    lowered = title.lower()
    return sum(1 for word in words if word in lowered)


def search(query: str, *, limit: int = 1, timeout: int = SEARCH_TIMEOUT) -> list[dict]:
    """Return up to ``limit`` reusable images for ``query``. Raises on transport errors."""
    params = urllib.parse.urlencode(
        {"q": query, "page_size": max(limit, OVER_FETCH), "license": LICENSES, "mature": "false"}
    )
    raw, _ = _get(f"{API_URL}?{params}", timeout)
    results = json.loads(raw.decode("utf-8")).get("results") or []
    hits = []
    for item in results:
        if not item.get("url"):
            continue
        version = str(item.get("license_version") or "").strip()
        license_name = str(item.get("license") or "").strip().upper()
        title = (item.get("title") or "").strip()
        hits.append(
            {
                "query": query,
                "url": item["url"],
                "title": title,
                "creator": (item.get("creator") or "").strip(),
                "license": f"{license_name} {version}".strip(),
                "source_page": item.get("foreign_landing_url") or "",
            }
        )
    # Stable sort keeps Openverse's own order among equally-relevant titles.
    hits.sort(key=lambda hit: relevance(hit["title"], query), reverse=True)
    return hits[:limit]


def download(hit: dict, dest_dir: str, index: int) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    last: Exception | None = None
    for _ in range(DOWNLOAD_ATTEMPTS):
        try:
            data, content_type = _get(hit["url"], DOWNLOAD_TIMEOUT)
            break
        except ImageSearchError:
            raise
        except Exception as exc:  # noqa: BLE001 - one slow origin should not lose the image
            last = exc
    else:
        raise ImageSearchError(f"download failed after {DOWNLOAD_ATTEMPTS} tries: {last!r}")

    if not content_type.startswith("image/"):
        raise ImageSearchError(f"not an image: {content_type or 'unknown'}")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageSearchError("image exceeds size cap")
    ext = image_ext(data)
    if ext is None:
        raise UnsupportedImageFormat(f"cannot embed {content_type or 'unknown'} in a slide")
    path = os.path.join(dest_dir, f"slide-image-{index:02d}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    hit["path"] = path
    return path


def fetch(queries: list[str], dest_dir: str) -> tuple[list[str | None], list[dict], list[str]]:
    """Best-effort fetch, one image per query. Never raises.

    Returns ``(paths, credits, warnings)``. ``paths`` keeps one slot per query --
    ``None`` where no image was found -- so slide alignment survives a partial failure.
    """
    if disabled():
        return [], [], ["image_search_disabled"]

    paths: list[str | None] = []
    credits: list[dict] = []
    warnings: list[str] = []

    for index, raw_query in enumerate(queries, 1):
        query = (raw_query or "").strip()
        if not query:
            paths.append(None)
            continue
        try:
            hits = search(query, limit=CANDIDATES)
        except Exception as exc:  # noqa: BLE001 - a dead API must not kill the deck
            warnings.append(f"image_search_failed:{query}:{type(exc).__name__}")
            paths.append(None)
            continue
        if not hits:
            warnings.append(f"image_search_no_result:{query}")
            paths.append(None)
            continue
        # The best-ranked hit may be a WebP or a dead origin. Walk down the ranking
        # rather than dropping the slide's picture on the first failure.
        for hit in hits:
            try:
                paths.append(download(hit, dest_dir, index))
                credits.append(hit)
                break
            except UnsupportedImageFormat:
                warnings.append(f"image_unsupported_format:{query}")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"image_download_failed:{query}:{type(exc).__name__}")
        else:
            paths.append(None)

    return paths, credits, warnings
