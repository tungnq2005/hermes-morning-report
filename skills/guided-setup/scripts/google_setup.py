#!/usr/bin/env python3
"""Connect Google Workspace from a chat window. Prints JSON.

Four subcommands, in the order the conversation goes:

    status                     what exists already
    client   --file/--json/--client-id+--client-secret
                               store the Desktop OAuth client the user created
    start    [--scopes ...]    print the consent URL for the user to open
    finish   --redirect-url    exchange the URL they pasted back for a refresh token
    test                       prove it end to end with a real conversion

`start`/`finish` replace the SSH tunnel that authorize_google.py needs; see
helpers/google_chat_oauth.py for why that works.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import envfile  # noqa: E402
from helpers import google_chat_oauth as goauth  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
CONVERT_SCRIPT = SKILL_DIR.parent / "doc-convert" / "scripts" / "convert.py"

# Console errors the user can act on, in the words the agent should use.
ERROR_HELP = {
    "no_json_found": "That message did not contain the JSON file's contents. Ask the user "
                     "to open the downloaded file and paste everything from { to }, or to "
                     "send the client ID and client secret instead.",
    "wrong_client_type:web": "The OAuth client was created as 'Web application'. It has to "
                             "be 'Desktop app' — a web client would fail later with "
                             "redirect_uri_mismatch. Ask the user to create a new client "
                             "and choose Desktop app.",
    "wrong_client_type:unknown": "That JSON is not an OAuth client file. Ask the user to "
                                 "download the file from Credentials → the client they "
                                 "created → Download JSON.",
    "missing_client_fields": "The client ID or client secret is missing from what was sent.",
    "bad_client_id": "That does not look like a Google client ID — a real one ends with "
                     "'.apps.googleusercontent.com'.",
    "no_client_secret": "No OAuth client is stored yet. Run the `client` step first.",
    "no_pending_authorization": "No authorization is in progress. Run the `start` step "
                                "and send the user the new link.",
    "authorization_expired": "That authorization link is more than an hour old. Run `start` "
                             "again and send the user a fresh link.",
    "no_code_in_url": "The pasted text has no authorization code in it. Ask the user to "
                      "copy the FULL address from the browser's address bar after pressing "
                      "Allow — the page showing an error is expected, the address is what "
                      "matters.",
    "no_refresh_token": "Google returned no refresh token, so access would die within the "
                        "hour. This happens when the same account has authorized before: "
                        "ask the user to remove the app at "
                        "https://myaccount.google.com/permissions and run `start` again.",
    "state_mismatch": "That link belongs to an older authorization attempt. Run `start` "
                      "again and use the newest link only.",
}


def help_for(code: str) -> str:
    if code in ERROR_HELP:
        return ERROR_HELP[code]
    if code.startswith("consent_error:access_denied"):
        return ("The user pressed Cancel, or the app is still in Testing mode and their "
                "account is not on the test-user list. Publishing the app fixes the second "
                "case; then run `start` again.")
    if code.startswith("consent_error:"):
        return f"Google refused the consent: {code.split(':', 1)[1]}. Run `start` again."
    if code.startswith("token_exchange_failed:invalid_grant"):
        return ("The authorization code was already used or is older than a few minutes. "
                "Run `start` again and ask the user to finish within a couple of minutes.")
    if code.startswith("token_exchange_failed:"):
        return f"Google rejected the exchange: {code.split(':', 1)[1]}."
    if code.startswith("invalid_json:"):
        return ("The pasted text is not valid JSON — it was probably cut short. Ask for the "
                "whole file contents again.")
    return "Report this exact code to the operator."


def fail(code: str, **extra) -> dict:
    return {"success": False, "error": code, "next_action":
            "Reply in the user's language. " + help_for(code), **extra}


def creds_dir_from(args) -> Path:
    env = envfile.read_env()
    return goauth.resolve_creds_dir(getattr(args, "creds_dir", None),
                                    env.get("DOC_CONVERT_GCREDS_DIR"))


def scope_set_from(args, creds_dir: Path) -> str:
    if getattr(args, "scopes", None):
        return args.scopes
    stored = envfile.read_env().get("DOC_CONVERT_GOOGLE_SCOPES", "").strip().lower()
    if stored in goauth.SCOPE_SETS:
        return stored
    return goauth.DEFAULT_SCOPE_SET


# -- subcommands --------------------------------------------------------
def cmd_status(args) -> dict:
    creds_dir = creds_dir_from(args)
    scopes = goauth.token_scopes(creds_dir)
    return {
        "success": True,
        "creds_dir": str(creds_dir),
        "client_secret": (creds_dir / "client_secret.json").exists(),
        "token": (creds_dir / "token.json").exists(),
        "pending_authorization": (creds_dir / goauth.PENDING_FILE).exists(),
        "granted_scopes": scopes,
        "can_read_private_links": goauth.SCOPE_DRIVE_READONLY in scopes,
        "next_action": "Reply in the user's language with what is connected. If token is "
                       "false, continue the flow from the first step that is not done.",
    }


def cmd_client(args) -> dict:
    creds_dir = creds_dir_from(args)
    try:
        if args.client_id or args.client_secret:
            data = goauth.client_json_from_pair(args.client_id or "", args.client_secret or "")
        else:
            raw = args.json
            if args.file:
                raw = Path(args.file).expanduser().read_text(encoding="utf-8")
            elif raw is None:
                raw = sys.stdin.read()
            data = goauth.parse_client_json(raw)
    except goauth.GoogleSetupError as err:
        return fail(str(err))
    except OSError as err:
        return fail("no_json_found", detail=str(err))

    path = goauth.write_client_json(creds_dir, data)
    link = "skipped" if args.no_link else goauth.link_into_default(creds_dir)
    scope_set = scope_set_from(args, creds_dir)
    # Written for the terminal path (06_google_oauth_hermes.sh) and for operators reading
    # the file; the symlink above is what makes doc-convert work regardless.
    envfile.set_env("DOC_CONVERT_GCREDS_DIR", str(creds_dir))
    envfile.set_env("DOC_CONVERT_GOOGLE_SCOPES", scope_set)
    return {
        "success": True,
        "client_secret_path": str(path),
        "creds_dir": str(creds_dir),
        "default_path_link": link,
        "client_id_tail": data["installed"]["client_id"][-30:],
        "next_action": "Reply in the user's language: the Google app is registered. Then "
                       "run google_setup.py start and send the user the link it prints.",
    }


def cmd_start(args) -> dict:
    creds_dir = creds_dir_from(args)
    scope_set = scope_set_from(args, creds_dir)
    try:
        started = goauth.build_auth_url(creds_dir, scope_set, args.port)
    except goauth.GoogleSetupError as err:
        return fail(str(err))
    envfile.set_env("DOC_CONVERT_GOOGLE_SCOPES", scope_set)
    return {
        "success": True,
        "auth_url": started["auth_url"],
        "scope_set": scope_set,
        "scopes": started["scopes"],
        "creds_dir": str(creds_dir),
        "next_action":
            "Reply in the user's language and send the auth_url as a plain clickable link "
            "in its own message. Tell the user, in this order: (1) open it and pick the "
            "Google account whose Drive the files should live in; (2) press Allow; (3) the "
            "browser will then show an error page such as 'This site can't be reached' — "
            "that is expected and means it worked; (4) copy the WHOLE address from the "
            "address bar and paste it here. Then run google_setup.py finish "
            "--redirect-url with what they pasted. The link is valid for one hour."
            + (" With the private-links scope the user will also see a 'Google hasn't "
               "verified this app' screen: they must tap Advanced, then 'Go to ... "
               "(unsafe)'." if scope_set == "private-links" else ""),
    }


def cmd_finish(args) -> dict:
    creds_dir = creds_dir_from(args)
    # A redirect URL is full of & and ? and arrives as whatever the user copied, so the
    # safest way for the agent to hand it over is a heredoc on stdin rather than an
    # argument the shell gets to reinterpret.
    pasted = args.redirect_url if args.redirect_url is not None else sys.stdin.read()
    try:
        pending = goauth.read_pending(creds_dir)
        code, state = goauth.extract_code(pasted)
        if state and state != pending["state"]:
            return fail("state_mismatch")
        token_data = goauth.exchange_code(creds_dir, code, pending)
        client = goauth.read_client_json(creds_dir)["installed"]
    except goauth.GoogleSetupError as err:
        return fail(str(err))

    path = goauth.write_token(creds_dir, token_data, client, pending["scopes"])
    account = goauth.whoami(token_data.get("access_token", ""))
    granted = goauth.token_scopes(creds_dir)
    return {
        "success": True,
        "token_path": str(path),
        "creds_dir": str(creds_dir),
        "account": account,
        "granted_scopes": granted,
        "can_read_private_links": goauth.SCOPE_DRIVE_READONLY in granted,
        "next_action":
            "Reply in the user's language: Google is connected"
            + (f" for the account {account}" if account else "")
            + ". Ask the user to confirm that is the right account — every file the bot "
              "creates lands in that account's Drive, privately. Then offer to run a test "
              "conversion (google_setup.py test).",
    }


def cmd_test(args) -> dict:
    """One real conversion, because a stored token is not proof that Drive accepts it."""
    creds_dir = creds_dir_from(args)
    if not (creds_dir / "token.json").exists():
        return {"success": False, "error": "not_authorized_yet",
                "creds_dir": str(creds_dir),
                "next_action": "Reply in the user's language: Google is not connected yet, "
                               "so there is nothing to test. Continue the flow from the "
                               "`start` step (or `client` if no OAuth client is stored)."}
    if not CONVERT_SCRIPT.exists():
        return {"success": False, "error": "convert_script_missing",
                "path": str(CONVERT_SCRIPT),
                "next_action": "Tell the user the doc-convert skill is not installed next to "
                               "this one; the operator needs to re-run setup step 04."}

    with tempfile.TemporaryDirectory(prefix="guided-setup-") as tmp:
        sample = Path(tmp) / "ket-noi-google.md"
        sample.write_text(
            "# Kiểm tra kết nối Google\n\n"
            "Đây là file thử do trợ lý tạo để kiểm tra kết nối Google Workspace.\n"
            "Bạn có thể xoá file này trong Drive bất cứ lúc nào.\n",
            encoding="utf-8")
        process = subprocess.run(
            [sys.executable, str(CONVERT_SCRIPT), "--input", str(sample),
             "--to", "gdoc", "--outdir", tmp],
            capture_output=True, text=True, timeout=600)
    try:
        manifest = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"success": False, "error": "convert_failed",
                "stderr": process.stderr[-1500:],
                "next_action": "Tell the user the test conversion failed and relay the "
                               "stderr text to the operator. Do not claim Google works."}

    ok = bool(manifest.get("success")) and manifest.get("render_engine") == "google"
    return {
        "success": ok,
        "render_engine": manifest.get("render_engine"),
        "google_url": manifest.get("google_url"),
        "warnings": manifest.get("warnings"),
        "next_action":
            ("Reply in the user's language: the test worked. Send google_url as a clickable "
             "link and tell the user the file is private in their Drive and safe to delete. "
             "Setup is now complete."
             if ok else
             "The conversion did not render in Google (render_engine is not 'google'). Tell "
             "the user honestly, relay warnings, and re-check google_setup.py status."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect Google Workspace from chat")
    parser.add_argument("--creds-dir", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="What is connected already")

    client = sub.add_parser("client", help="Store the Desktop OAuth client")
    client.add_argument("--file", help="Path to a client_secret json file the user sent")
    client.add_argument("--json", help="The JSON contents the user pasted")
    client.add_argument("--client-id", dest="client_id")
    client.add_argument("--client-secret", dest="client_secret")
    client.add_argument("--scopes", choices=sorted(goauth.SCOPE_SETS))
    client.add_argument("--no-link", dest="no_link", action="store_true",
                        help="Do not symlink the credentials into doc-convert's default path")

    start = sub.add_parser("start", help="Print the consent link for the user")
    start.add_argument("--scopes", choices=sorted(goauth.SCOPE_SETS))
    start.add_argument("--port", type=int, default=goauth.DEFAULT_PORT)

    finish = sub.add_parser("finish", help="Exchange the URL the user pasted back")
    finish.add_argument("--redirect-url", help="What the user pasted; omit to read stdin")

    sub.add_parser("test", help="Run one real conversion through Google")

    args = parser.parse_args()
    handlers = {"status": cmd_status, "client": cmd_client, "start": cmd_start,
                "finish": cmd_finish, "test": cmd_test}
    result = handlers[args.command](args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
