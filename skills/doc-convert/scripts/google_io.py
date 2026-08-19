"""Google Workspace integration for doc-convert.

Reads PRIVATE Google Docs/Slides/Drive files (unlike the public curl path in doc_io),
imports a locally built .pptx/.docx into Google Slides / Google Docs, and exports a
Google file back out to pdf/pptx/docx.

Google is the renderer of record: the deck the customer opens is the one Google
Slides draws, identically on macOS, Windows, iPad and the browser. Files handed back
to the user are Google's export, not python-pptx's or LibreOffice's output.

Credentials live under the skill state dir:
    state/google-creds/client_secret.json   (OAuth desktop client, provided by operator)
    state/google-creds/token.json           (created by authorize_google.py, one-time)

All functions raise GoogleAuthError with actionable text when auth/token is missing.
"""
from __future__ import annotations

import io
import os
import re

# Scopes decide how hard this is to deploy, so the set is kept as small as the features
# in use allow.
#
# `drive.file` covers everything the conversion pipeline does: it uploads the built
# Office file, exports the Google copy back to pdf/pptx/docx, and reads the deck back
# through the Slides API -- all on files this app created itself. Google classes it as
# non-sensitive, so an OAuth client that asks for nothing else can be published without
# verification, shows no "unverified app" warning, and its refresh tokens do not expire
# after seven days the way a Testing-mode client's do. That is a one-click setup for a
# customer.
#
# `drive.readonly` is the price of the "paste a private Google link" feature: it reads
# files this app did not create, which Google classes as RESTRICTED -- app verification
# plus an annual CASA security assessment before it can be published. A deployment that
# wants that feature opts in and accepts the heavier setup.
#
# The `documents` and `presentations` scopes were dropped: they were needed by the old
# builders that assembled Docs and Slides through batchUpdate. Content now arrives by
# import, and the Slides readback works under `drive.file`.
SCOPE_DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"
SCOPE_DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"

SCOPE_SETS = {
    "minimal": [SCOPE_DRIVE_FILE],
    "private-links": [SCOPE_DRIVE_FILE, SCOPE_DRIVE_READONLY],
}
DEFAULT_SCOPE_SET = "private-links"


def scope_set_name() -> str:
    name = (os.environ.get("DOC_CONVERT_GOOGLE_SCOPES") or DEFAULT_SCOPE_SET).strip().lower()
    return name if name in SCOPE_SETS else DEFAULT_SCOPE_SET


SCOPES = SCOPE_SETS[scope_set_name()]

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Env override lets tests/deployments point elsewhere; defaults to the skill state dir.
DEFAULT_CREDS_DIR = os.environ.get("DOC_CONVERT_GCREDS_DIR") or os.path.join(
    SKILL_DIR, "state", "google-creds")

_DOC_RE = re.compile(r"docs\.google\.com/document/d/([\w-]+)")
_SLIDES_RE = re.compile(r"docs\.google\.com/presentation/d/([\w-]+)")
_DRIVE_RE = re.compile(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?.*id=)([\w-]+)")

# Google-native mime types -> (export mime, output extension)
_EXPORT_MAP = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
}


class GoogleAuthError(Exception):
    """Raised when credentials/token are missing or invalid."""


def is_google_url(value: str) -> bool:
    return bool(_DOC_RE.search(value) or _SLIDES_RE.search(value) or _DRIVE_RE.search(value))


def extract_file_id(value: str) -> str | None:
    for rx in (_DOC_RE, _SLIDES_RE, _DRIVE_RE):
        m = rx.search(value)
        if m:
            return m.group(1)
    # bare id
    if re.fullmatch(r"[\w-]{20,}", value.strip()):
        return value.strip()
    return None


def has_token(creds_dir: str = DEFAULT_CREDS_DIR) -> bool:
    return os.path.exists(os.path.join(creds_dir, "token.json"))


def granted_scopes(creds_dir: str = DEFAULT_CREDS_DIR) -> list[str]:
    """Scopes the stored token was actually granted -- not the ones this build asks for.

    A deployment authorized under one scope set keeps working after the code's default
    changes, so the token file is the only honest source.
    """
    token_path = os.path.join(creds_dir, "token.json")
    try:
        import json

        with open(token_path, encoding="utf-8") as fh:
            return list(json.load(fh).get("scopes") or [])
    except Exception:  # noqa: BLE001 - missing or unreadable token grants nothing
        return []


def can_read_private_files(creds_dir: str = DEFAULT_CREDS_DIR) -> bool:
    return SCOPE_DRIVE_READONLY in granted_scopes(creds_dir)


def load_credentials(creds_dir: str = DEFAULT_CREDS_DIR):
    """Load stored token, refresh if expired. Raises GoogleAuthError if unusable."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = os.path.join(creds_dir, "token.json")
    if not os.path.exists(token_path):
        raise GoogleAuthError(
            "Chưa authorize Google. Chạy 1 lần: "
            "python3 skills/doc-convert/scripts/authorize_google.py"
        )
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())
        else:
            raise GoogleAuthError("Google token hết hạn và không refresh được. Chạy lại authorize_google.py.")
    return creds


def _drive_service(creds):
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def download_private(url_or_id: str, dest_dir: str, creds_dir: str = DEFAULT_CREDS_DIR) -> str:
    """Download/export a private Google file. Returns local path (docx/pptx/xlsx or original)."""
    from googleapiclient.http import MediaIoBaseDownload

    if not can_read_private_files(creds_dir):
        # A minimal-scope deployment can only touch files it created itself. Say so
        # plainly instead of letting Drive answer with a bare 403.
        raise GoogleAuthError(
            "Bản cài đặt này chỉ có quyền với file do bot tạo, không đọc được link Google "
            "riêng tư. Hãy tải file lên trực tiếp, hoặc bật chia sẻ 'Bất kỳ ai có link'. "
            "Nếu cần đọc Drive riêng tư, authorize lại với "
            "DOC_CONVERT_GOOGLE_SCOPES=private-links."
        )

    creds = load_credentials(creds_dir)
    file_id = extract_file_id(url_or_id)
    if not file_id:
        raise GoogleAuthError(f"Không tách được Google file id từ: {url_or_id}")

    os.makedirs(dest_dir, exist_ok=True)
    drive = _drive_service(creds)
    meta = drive.files().get(fileId=file_id, fields="name,mimeType",
                             supportsAllDrives=True).execute()
    name = re.sub(r"[^\w.-]", "_", meta.get("name", "gdrive-file"))
    mime = meta.get("mimeType", "")

    if mime in _EXPORT_MAP:
        export_mime, ext = _EXPORT_MAP[mime]
        request = drive.files().export_media(fileId=file_id, mimeType=export_mime)
        if not name.endswith(ext):
            name += ext
    else:
        request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)

    dest = os.path.join(dest_dir, name)
    buf = io.FileIO(dest, "wb")
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.close()
    return dest


# --- direct to cloud ----------------------------------------------------------
# A Google file is produced by importing the locally built Office file, never by
# assembling slides through the Slides API. The pptx builder already owns the whole
# visual identity (cover, dividers, stat cards, card grid, imagery); rebuilding that
# through batchUpdate requests would be a second, divergent layout engine. Drive's
# importer converts the deck into a native Google Slides file, so the customer opens
# the same design on macOS, Windows, iPad or a browser -- and any file they still
# want is exported back out of Google rather than rendered by python-pptx or
# LibreOffice, whose output is what rendered wrong in PowerPoint for Mac.
_IMPORT_KINDS = {
    "gslides": {
        "ext": ".pptx",
        "source_mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "google_mime": "application/vnd.google-apps.presentation",
        "url": "https://docs.google.com/presentation/d/{id}/edit",
    },
    "gdoc": {
        "ext": ".docx",
        "source_mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "google_mime": "application/vnd.google-apps.document",
        "url": "https://docs.google.com/document/d/{id}/edit",
    },
}

# Formats Drive can export a native Google file back to.
EXPORT_MIMES = {
    "pdf": ("application/pdf", ".pdf"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
}

# Drive's export endpoint refuses anything above 10 MB. A photo-heavy deck can cross
# that, so callers treat an export failure as a warning and still deliver the link.
EXPORT_SIZE_LIMIT_MB = 10

EMU_PER_PT = 12700


class GoogleExportError(Exception):
    """Raised when a Drive export fails (size cap, transient API error)."""


def import_local(path: str, kind: str, title: str = "",
                 creds_dir: str = DEFAULT_CREDS_DIR) -> dict:
    """Upload a local .pptx/.docx and let Drive convert it to a native Google file.

    Returns {id, url, name, kind}.
    """
    from googleapiclient.http import MediaFileUpload

    spec = _IMPORT_KINDS.get(kind)
    if not spec:
        raise GoogleAuthError(f"Unknown cloud target: {kind}")
    if not os.path.exists(path):
        raise GoogleAuthError(f"Không tìm thấy file để upload: {path}")
    if os.path.splitext(path)[1].lower() != spec["ext"]:
        # Drive answers a mismatched mime with an opaque "cannot convert" error.
        raise GoogleAuthError(
            f"{kind} cần file {spec['ext']}, nhận được {os.path.basename(path)}")

    creds = load_credentials(creds_dir)
    drive = _drive_service(creds)
    media = MediaFileUpload(path, mimetype=spec["source_mime"], resumable=False)
    body = {
        "name": (title or os.path.splitext(os.path.basename(path))[0])[:200],
        "mimeType": spec["google_mime"],
    }
    created = drive.files().create(body=body, media_body=media, fields="id,name",
                                   supportsAllDrives=True).execute()
    file_id = created["id"]
    return {"id": file_id, "url": spec["url"].format(id=file_id),
            "name": created.get("name", body["name"]), "kind": kind}


def export_to(file_id: str, fmt: str, dest_path: str,
              creds_dir: str = DEFAULT_CREDS_DIR) -> str:
    """Export a native Google file to pdf/pptx/docx.

    Google does the rendering here, so the file the customer downloads is the one
    Google Slides/Docs shows -- not python-pptx's or LibreOffice's interpretation.
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload

    if fmt not in EXPORT_MIMES:
        raise GoogleExportError(f"Unsupported export format: {fmt}")
    mime, _ext = EXPORT_MIMES[fmt]

    creds = load_credentials(creds_dir)
    drive = _drive_service(creds)
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    request = drive.files().export_media(fileId=file_id, mimeType=mime)
    buf = io.FileIO(dest_path, "wb")
    try:
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except HttpError as err:
        buf.close()
        if os.path.exists(dest_path):
            os.remove(dest_path)
        status = getattr(err.resp, "status", None)
        if status in (403, 413):
            raise GoogleExportError(
                f"Drive từ chối export {fmt} (giới hạn {EXPORT_SIZE_LIMIT_MB}MB): {err}") from err
        raise GoogleExportError(f"Drive export {fmt} thất bại: {err}") from err
    finally:
        if not buf.closed:
            buf.close()
    return dest_path


def _rgb(color: dict | None) -> tuple | None:
    """(r, g, b) from a Slides colour, or None when the colour is inherited/themed."""
    if not color:
        return None
    opaque = color.get("opaqueColor") or color
    rgb = opaque.get("rgbColor")
    if rgb is None:
        return None
    return tuple(int(round(float(rgb.get(channel, 0)) * 255))
                 for channel in ("red", "green", "blue"))


def _length_emu(value: dict | None, scale: float = 1.0) -> float:
    """Slides lengths are {magnitude, unit} with unit EMU or PT."""
    if not value:
        return 0.0
    magnitude = float(value.get("magnitude", 0) or 0) * scale
    return magnitude * EMU_PER_PT if value.get("unit") == "PT" else magnitude


def inspect_presentation(url_or_id: str, creds_dir: str = DEFAULT_CREDS_DIR) -> dict:
    """Read a created deck back out of the Slides API.

    The import is Google's code, not ours, so the only honest way to know the deck
    survived it is to ask Google what the deck now holds. Returns the page size plus,
    per slide, every text box with its rendered geometry and font size.
    """
    from googleapiclient.discovery import build

    creds = load_credentials(creds_dir)
    pres_id = extract_file_id(url_or_id) or url_or_id.strip()
    api = build("slides", "v1", credentials=creds, cache_discovery=False)
    # foregroundColor is fetched because Drive's importer drops any colour we wrote at
    # paragraph level and repaints the run from its own layout: a title that is white in
    # the .pptx can come back as the theme's dark ink, invisible on a dark slide.
    fields = ("pageSize,slides(objectId,pageProperties(pageBackgroundFill(solidFill(color)))"
              ",pageElements(objectId,size,transform,image(contentUrl),shape(shapeType,"
              "text(textElements(textRun(content,style(fontSize,bold,foregroundColor)))))))")
    pres = api.presentations().get(presentationId=pres_id, fields=fields).execute()

    page = pres.get("pageSize", {}) or {}
    out: dict = {
        "id": pres_id,
        "page": {"width_emu": _length_emu(page.get("width")),
                 "height_emu": _length_emu(page.get("height"))},
        "slides": [],
    }
    for index, slide in enumerate(pres.get("slides", [])):
        page_fill = ((slide.get("pageProperties") or {}).get("pageBackgroundFill") or {})
        entry: dict = {"index": index, "texts": [], "images": 0,
                       "background": _rgb((page_fill.get("solidFill") or {}).get("color"))}
        for element in slide.get("pageElements", []):
            transform = element.get("transform", {}) or {}
            unit = transform.get("unit", "EMU")
            size = element.get("size", {}) or {}
            box = {
                "left_emu": _length_emu({"magnitude": transform.get("translateX", 0), "unit": unit}),
                "top_emu": _length_emu({"magnitude": transform.get("translateY", 0), "unit": unit}),
                "width_emu": _length_emu(size.get("width"), float(transform.get("scaleX", 1) or 1)),
                "height_emu": _length_emu(size.get("height"), float(transform.get("scaleY", 1) or 1)),
            }
            if element.get("image"):
                entry["images"] += 1
                continue
            shape = element.get("shape") or {}
            text_elements = ((shape.get("text") or {}).get("textElements") or [])
            runs = [te.get("textRun") for te in text_elements if te.get("textRun")]
            content = "".join(r.get("content", "") for r in runs)
            if not content.strip():
                continue
            sizes = [float(((r.get("style") or {}).get("fontSize") or {}).get("magnitude", 0) or 0)
                     for r in runs]
            sizes = [s for s in sizes if s > 0]
            # One entry per run colour: a run whose colour is None inherited it from
            # Google's own layout, which is the failure mode worth reporting.
            colours = []
            for run in runs:
                if not run.get("content", "").strip():
                    continue
                style = run.get("style") or {}
                colours.append({
                    "text": run["content"].strip(),
                    "rgb": _rgb(style.get("foregroundColor")),
                    "font_pt": float((style.get("fontSize") or {}).get("magnitude", 0) or 0) or None,
                    "bold": bool(style.get("bold")),
                })
            entry["texts"].append({
                "object_id": element.get("objectId", ""),
                "text": content,
                "font_pt": max(sizes) if sizes else None,
                "runs": colours,
                **box,
            })
        out["slides"].append(entry)
    return out
