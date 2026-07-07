"""Google Workspace integration for doc-convert.

Reads PRIVATE Google Docs/Slides/Drive files (unlike the public curl path in doc_io)
and creates "direct to cloud" drafts in Google Docs / Slides.

Credentials live under the skill state dir:
    state/google-creds/client_secret.json   (OAuth desktop client, provided by operator)
    state/google-creds/token.json           (created by authorize_google.py, one-time)

All functions raise GoogleAuthError with actionable text when auth/token is missing.
"""
from __future__ import annotations

import io
import os
import re

# Least-privilege scopes: read any file the user can access + manage app-created files
# + create/edit Docs and Slides content.
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations",
]

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


def create_google_doc(title: str, doc: dict, creds_dir: str = DEFAULT_CREDS_DIR) -> dict:
    """Create a new Google Doc from an extracted-document dict. Returns {id, url}."""
    from googleapiclient.discovery import build

    creds = load_credentials(creds_dir)
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    created = docs.documents().create(body={"title": title or doc.get("title", "Untitled")}).execute()
    doc_id = created["documentId"]

    # Build a single insert at index 1; Docs inserts push content down, so build text top-down
    # but send requests bottom-up to keep indices valid. Simpler: assemble full text, one insert.
    lines = []
    for b in doc.get("blocks", []):
        if b["kind"] == "heading":
            lines.append(b["text"])
        elif b["kind"] == "bullet":
            lines.append("• " + b["text"])
        else:
            lines.append(b["text"])
    text = "\n".join(lines) + "\n"
    if text.strip():
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
        ).execute()
    return {"id": doc_id, "url": f"https://docs.google.com/document/d/{doc_id}/edit"}


def create_google_slides(title: str, sections: list[dict], creds_dir: str = DEFAULT_CREDS_DIR) -> dict:
    """Create a new Google Slides deck from outline sections. Returns {id, url, slides}."""
    from googleapiclient.discovery import build

    creds = load_credentials(creds_dir)
    slides = build("slides", "v1", credentials=creds, cache_discovery=False)
    pres = slides.presentations().create(body={"title": title or "Untitled"}).execute()
    pres_id = pres["presentationId"]

    requests = []
    for i, sec in enumerate(sections):
        slide_id = f"slide_{i}"
        title_id = f"title_{i}"
        body_id = f"body_{i}"
        requests.append({"createSlide": {
            "objectId": slide_id,
            "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
            "placeholderIdMappings": [
                {"layoutPlaceholder": {"type": "TITLE"}, "objectId": title_id},
                {"layoutPlaceholder": {"type": "BODY"}, "objectId": body_id},
            ],
        }})
        requests.append({"insertText": {"objectId": title_id, "text": (sec.get("title") or title)[:180]}})
        body_text = "\n".join("• " + t for t in sec.get("items", []) if t)
        if body_text:
            requests.append({"insertText": {"objectId": body_id, "text": body_text}})
    if requests:
        slides.presentations().batchUpdate(
            presentationId=pres_id, body={"requests": requests}).execute()
    return {"id": pres_id, "slides": len(sections),
            "url": f"https://docs.google.com/presentation/d/{pres_id}/edit"}
