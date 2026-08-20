#!/usr/bin/env python3
"""What is connected, what is missing, and what to ask the user for next. Prints JSON.

This is the entry point of every guided-setup conversation, including the ones that
start as "the morning report stopped working". Presence is checked by default because
it is instant; `--verify` additionally calls each provider so an expired or revoked key
is caught here rather than at 6am tomorrow.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import envfile, keyspec  # noqa: E402
from helpers import google_chat_oauth as goauth  # noqa: E402

# Set by the installer wizard (setup step 02), never by this skill: without them the
# bot could not be reading this message at all. Reported only so a support conversation
# can see the whole picture at once.
INSTALLER_KEYS = ("TELEGRAM_BOT_TOKEN", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def key_items(env: dict[str, str], verify: bool) -> list[dict]:
    items = []
    for key_id, spec in keyspec.KEY_SPECS.items():
        value = env.get(spec["env"], "").strip()
        item = {
            "id": key_id,
            "env": spec["env"],
            "label_en": spec["label_en"],
            "label_vi": spec["label_vi"],
            "tier": spec["tier"],
            "used_by": spec["used_by"],
            "console": spec["console"],
            "guide_anchor": spec["guide_anchor"],
            "present": bool(value),
            "masked": envfile.mask(value),
            "status": "present" if value else "missing",
        }
        if value and verify:
            result = keyspec.verify(key_id, value)
            item["verify"] = result
            item["status"] = {"verified": "ok", "rejected": "invalid"}.get(
                result["state"], "unverified")
        items.append(item)
    return items


def google_item(env: dict[str, str], creds_dir: Path) -> dict:
    client_secret = (creds_dir / "client_secret.json").exists()
    token = (creds_dir / "token.json").exists()
    scopes = goauth.token_scopes(creds_dir)
    return {
        "id": "google",
        "label_en": "Google Workspace (Slides/Docs output)",
        "label_vi": "Google Workspace (xuất Slides/Docs)",
        "tier": "optional",
        "used_by": ["doc-convert"],
        "console": "https://console.cloud.google.com/",
        "guide_anchor": "google",
        "creds_dir": str(creds_dir),
        "client_secret": client_secret,
        "token": token,
        "granted_scopes": scopes,
        "can_read_private_links": goauth.SCOPE_DRIVE_READONLY in scopes,
        "pending_authorization": (creds_dir / goauth.PENDING_FILE).exists(),
        "present": token,
        "status": "ok" if token else ("client_only" if client_secret else "missing"),
        "env_file_creds_dir": env.get("DOC_CONVERT_GCREDS_DIR", ""),
        "process_creds_dir": os.environ.get("DOC_CONVERT_GCREDS_DIR", ""),
    }


def build_report(verify: bool, creds_dir_flag: str | None) -> dict:
    env = envfile.read_env()
    creds_dir = goauth.resolve_creds_dir(creds_dir_flag, env.get("DOC_CONVERT_GCREDS_DIR"))
    keys = key_items(env, verify)
    google = google_item(env, creds_dir)
    by_id = {item["id"]: item for item in keys}

    warnings: list[str] = []
    # Search is the only hard requirement: the collector tries Exa first and falls back
    # to Brave, so either one alone is a working Morning Report. Only an outright
    # rejection counts against it -- a key we could not reach is unproven, not broken,
    # and calling it broken sends the user to regenerate a key that works.
    search_ok = any(by_id[k]["present"] and by_id[k]["status"] != "invalid"
                    for k in ("exa", "brave"))
    for key_id in ("exa", "firecrawl", "brave"):
        if by_id[key_id]["status"] == "unverified":
            warnings.append(f"{key_id}_unverified:the provider could not be reached from "
                            "this server, so the stored key is unproven")
    if not by_id["firecrawl"]["present"]:
        warnings.append("firecrawl_missing:articles are fetched with a plain HTTP reader, "
                        "which returns less text on script-heavy news sites")
    if by_id["exa"]["present"] and not by_id["brave"]["present"]:
        warnings.append("brave_missing:no search fallback if Exa is down or out of credits")
    if google["status"] == "client_only":
        warnings.append("google_half_done:client saved but nobody has pressed Allow yet — "
                        "run google_setup.py start")
    if google["status"] == "missing":
        warnings.append("google_missing:doc-convert renders files locally, which can look "
                        "wrong in PowerPoint on macOS; gslides/gdoc targets fail")
    if google["env_file_creds_dir"] and not google["process_creds_dir"]:
        warnings.append("gcreds_env_not_exported:DOC_CONVERT_GCREDS_DIR is in ~/.hermes/.env "
                        "but not in the environment doc-convert runs in — google_setup.py "
                        "keeps a symlink at the default path so both resolve")

    missing = [item["id"] for item in keys if not item["present"]]
    if not google["token"]:
        missing.append("google")

    installer = {name: bool(env.get(name)) for name in INSTALLER_KEYS if env.get(name)}

    # Order matters: this is the sequence the agent walks the user through.
    order = ["exa", "firecrawl", "brave", "google"]
    next_step = next((step for step in order if step in missing), "")

    ready = {
        "morning_report": search_ok,
        "doc_convert_local": True,   # conversion itself never needed a key
        "doc_convert_google": google["token"],
    }
    return {
        "ready": ready,
        "keys": keys,
        "google": google,
        "installer_keys_present": installer,
        "env_file": str(envfile.env_path()),
        "verified": verify,
        "missing": missing,
        "next_step": next_step,
        "warnings": warnings,
        "next_action": next_action(ready, missing, next_step, verify),
    }


def next_action(ready: dict, missing: list[str], next_step: str, verified: bool) -> str:
    lines = ["Reply in the user's language. Do not paste raw JSON to the user; say what "
             "is connected and what is not, in one short list."]
    if not missing:
        lines.append("Everything is connected. Offer the two proof steps: a test morning "
                     "report (morning-report skill) and a test document conversion.")
    else:
        lines.append(
            f"Missing: {', '.join(missing)}. Guide the user through ONE item at a time, "
            f"starting with '{next_step}'. Read the matching section of "
            "references/key-guides.vi.md (or .en.md) and relay those steps as short "
            "numbered messages — never send the user a wall of text or a raw URL list. "
            "Wait for the user to paste the key, then save it with save_key.py "
            "(google uses google_setup.py instead).")
    if not ready["morning_report"]:
        lines.append("Morning Report cannot run yet: it needs Exa or Brave.")
    if not verified:
        lines.append("This check only looked for the keys' presence. Run with --verify to "
                     "prove each key still works before telling the user setup is done.")
    return " ".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report guided-setup status as JSON")
    parser.add_argument("--verify", action="store_true",
                        help="Also call each provider to prove the stored key still works")
    parser.add_argument("--creds-dir", default=None,
                        help="Override the Google credentials directory")
    args = parser.parse_args()
    print(json.dumps(build_report(args.verify, args.creds_dir),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
