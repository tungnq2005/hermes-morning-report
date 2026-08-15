#!/usr/bin/env python3
"""Runtime readiness check for the doc-convert skill. Prints JSON."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(os.path.dirname(SKILL_DIR))
# morning-report's TTS helper — path differs between skill versions (flat vs report/ layout).
TTS_HELPER_CANDIDATES = (
    os.path.join(WORKSPACE, "skills", "morning-report", "scripts", "generate_audio.py"),
    os.path.join(WORKSPACE, "skills", "morning-report", "scripts", "report", "generate_audio.py"),
    os.path.join(WORKSPACE, "skills", "morning-report", "scripts", "report", "generate_audio_file.py"),
)


def _font_check() -> dict:
    """Report whether the Calibri substitute the PDF target relies on is installed."""
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return {"ok": False, "carlito": False, "reason": "fc-list not available"}
    try:
        out = subprocess.run([fc_list, "-f", "%{family}\n"], capture_output=True,
                             text=True, timeout=20).stdout.lower()
    except Exception as err:  # noqa: BLE001 - a font probe must never block a conversion
        return {"ok": False, "carlito": False, "reason": str(err)}
    carlito = "carlito" in out or "calibri" in out
    return {"ok": carlito, "carlito": carlito}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compact", action="store_true")
    args = ap.parse_args()

    checks: dict = {"python_modules": {}, "binaries": {}, "paths": {}, "tts_helper": {}}
    problems: list[str] = []
    warnings: list[str] = []

    for mod, pkg in (("docx", "python-docx"), ("pptx", "python-pptx"), ("pypdf", "pypdf")):
        try:
            importlib.import_module(mod)
            checks["python_modules"][pkg] = {"ok": True}
        except Exception as err:
            checks["python_modules"][pkg] = {"ok": False, "error": str(err)}
            problems.append(f"missing python module: {pkg}")

    for binary, required in (("soffice", True), ("curl", True), ("ffmpeg", False)):
        path = shutil.which(binary)
        checks["binaries"][binary] = {"ok": bool(path), "path": path, "required": required}
        if required and not path:
            problems.append(f"missing binary: {binary}")

    # The docx and pdf targets pin Calibri, which ships with Office but not with Linux.
    # LibreOffice substitutes Carlito -- metric-compatible and complete for Vietnamese --
    # but only when fonts-crosextra-carlito is installed. Without it the substitute is
    # picked at random and Vietnamese diacritics come out as boxes in the PDF.
    checks["fonts"] = _font_check()
    if not checks["fonts"]["ok"]:
        warnings.append(
            "Carlito not installed - LibreOffice will substitute an arbitrary font for "
            "Calibri and Vietnamese diacritics may render as boxes in PDF output. "
            "Install with: sudo apt-get install -y fonts-crosextra-carlito"
        )

    for name, rel in (("output_history", "state/output-history"), ("audio_history", "state/audio-history")):
        path = os.path.join(SKILL_DIR, rel)
        os.makedirs(path, exist_ok=True)
        ok = os.path.isdir(path) and os.access(path, os.W_OK)
        checks["paths"][name] = {"path": path, "ok": ok}
        if not ok:
            problems.append(f"path not writable: {path}")

    # TTS helper is OPTIONAL (narration only). Conversion — the core capability — never needs it,
    # so a missing helper is a warning, not a blocker.
    tts_path = next((p for p in TTS_HELPER_CANDIDATES if os.path.exists(p)), None)
    checks["tts_helper"] = {"path": tts_path, "ok": bool(tts_path),
                            "candidates": list(TTS_HELPER_CANDIDATES)}
    if not tts_path:
        warnings.append("morning-report TTS helper not found - narration disabled (conversion still works)")

    # Google Workspace (optional feature): libs + credentials + authorized token.
    creds_dir = os.path.join(SKILL_DIR, "state", "google-creds")
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        g_libs = True
    except Exception:
        g_libs = False
    checks["google"] = {
        "libs_installed": g_libs,
        "client_secret": os.path.exists(os.path.join(creds_dir, "client_secret.json")),
        "authorized_token": os.path.exists(os.path.join(creds_dir, "token.json")),
    }
    # Google is optional; do NOT add to problems (private-Google/direct-to-cloud just stay disabled).

    result = {"success": len(problems) == 0, "environment_ok": len(problems) == 0,
              "problems": problems, "warnings": warnings, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
