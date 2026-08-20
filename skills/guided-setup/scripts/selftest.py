#!/usr/bin/env python3
"""Rehearse the entire guided-setup flow, offline, before a real user ever tries it.

Everything except Google is exercised for real: the actual CLIs are run as subprocesses,
against a throwaway HERMES_HOME and a throwaway credentials directory, so nothing here
touches the live install. Google is the one part that cannot be rehearsed against the
real thing without a Google account, so a local stub stands in for its token endpoint --
which still proves the parts that break in practice: how the request is encoded, how
failures are reported, and whether the token file we write can be read back by the
library doc-convert loads it with.

    python3 skills/guided-setup/scripts/selftest.py          # summary
    python3 skills/guided-setup/scripts/selftest.py --json   # machine-readable

Exit code 0 means the flow is wired correctly end to end. It does NOT mean the user's
keys work -- that is `check_setup.py --verify` -- nor that Google consent works with a
real project, which is the manual checklist in docs/google-oauth-setup.vi.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from helpers import envfile  # noqa: E402
from helpers import google_chat_oauth as goauth  # noqa: E402

CLIENT_ID = "1234567890-selftest.apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-selftest-secret"
FAKE_ACCOUNT = "nguoidung@example.com"


# -- the stand-in for Google -------------------------------------------
class StubGoogle:
    """Minimal stand-in for Google's token and Drive endpoints.

    `mode` selects which of the three answers that actually matter in production it
    gives back: a normal grant, a rejected/expired code, or the silent one -- a grant
    with no refresh token, which looks fine for an hour and then locks the bot out.
    """

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.last_token_request: dict[str, list[str]] = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: A003 - silence the default stderr log
                pass

            def _send(self, status: int, payload: dict):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
                length = int(self.headers.get("Content-Length", 0))
                stub.last_token_request = parse_qs(self.rfile.read(length).decode())
                if stub.mode == "invalid_grant":
                    self._send(400, {"error": "invalid_grant",
                                     "error_description": "Bad Request"})
                    return
                payload = {"access_token": "stub-access-token", "expires_in": 3599,
                           "scope": goauth.SCOPE_DRIVE_FILE, "token_type": "Bearer"}
                if stub.mode != "no_refresh":
                    payload["refresh_token"] = "stub-refresh-token"
                self._send(200, payload)

            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
                self._send(200, {"user": {"emailAddress": FAKE_ACCOUNT}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "StubGoogle":
        self._thread.start()
        self._saved = (goauth.TOKEN_ENDPOINT, goauth.DRIVE_ABOUT)
        goauth.TOKEN_ENDPOINT = f"http://127.0.0.1:{self.port}/token"
        goauth.DRIVE_ABOUT = f"http://127.0.0.1:{self.port}/about"
        return self

    def __exit__(self, *exc):
        goauth.TOKEN_ENDPOINT, goauth.DRIVE_ABOUT = self._saved
        self._server.shutdown()
        self._server.server_close()


# -- reporting ----------------------------------------------------------
class Report:
    def __init__(self):
        self.steps: list[dict] = []

    def step(self, name: str, ok: bool, detail: str = ""):
        self.steps.append({"step": name, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def failed(self) -> list[dict]:
        return [s for s in self.steps if not s["ok"]]


def run_cli(script: str, *args: str, env: dict, stdin: str | None = None) -> dict:
    """Run one of the skill's CLIs exactly as the agent would, and parse its JSON."""
    process = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, input=stdin, env=env, timeout=120)
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"success": False, "error": "not_json",
                "stdout": process.stdout[-500:], "stderr": process.stderr[-500:]}


def rehearse() -> Report:
    report = Report()
    home = Path(tempfile.mkdtemp(prefix="guided-setup-selftest-home-"))
    creds = Path(tempfile.mkdtemp(prefix="guided-setup-selftest-creds-"))
    env = dict(os.environ, HERMES_HOME=str(home))
    env.pop("DOC_CONVERT_GCREDS_DIR", None)
    try:
        # 1. A fresh install must name what is missing and where to start.
        first = run_cli("check_setup.py", "--creds-dir", str(creds), env=env)
        report.step(
            "Trạng thái ban đầu: liệt kê đúng cái còn thiếu",
            first.get("next_step") == "exa" and "google" in first.get("missing", []),
            f"next_step={first.get('next_step')} missing={first.get('missing')}")

        # 2. The messy paste a real user sends -- label, quotes, an extra line.
        saved = run_cli("save_key.py", "--name", "exa", "--no-verify", env=env,
                        stdin='Đây là key của mình nhé:\n"exa-selftest-key-0001"\n')
        report.step(
            "Nhận key dán lộn xộn (có nhãn, dấu nháy, xuống dòng)",
            saved.get("saved") and envfile.read_env(home / ".env").get(
                "EXA_API_KEY") == "exa-selftest-key-0001",
            f"masked={saved.get('masked')}")

        # 3. The key must never come back out in the JSON the agent reads aloud.
        report.step("Không đọc ngược key ra output",
                    "exa-selftest-key-0001" not in json.dumps(saved),
                    "")

        # 4. A URL instead of a key must be refused, not stored.
        refused = run_cli("save_key.py", "--name", "firecrawl", "--no-verify",
                          "--value", "https://www.firecrawl.dev/app/api-keys", env=env)
        report.step(
            "Từ chối khi người dùng dán nhầm địa chỉ web",
            refused.get("saved") is False
            and "FIRECRAWL_API_KEY" not in envfile.read_env(home / ".env"),
            f"problems={refused.get('problems')}")

        # 5. Registering the OAuth client from an ID + secret pair.
        client = run_cli("google_setup.py", "--creds-dir", str(creds), "client",
                         "--client-id", CLIENT_ID, "--client-secret", CLIENT_SECRET,
                         "--no-link", env=env)
        report.step("Lưu OAuth client (Desktop app)",
                    client.get("success") and (creds / "client_secret.json").exists(),
                    client.get("error", ""))

        # 6. A Web-application client is the mistake that only surfaces at consent time.
        web = run_cli("google_setup.py", "--creds-dir", str(creds), "client", "--no-link",
                      env=env, stdin=json.dumps({"web": {"client_id": CLIENT_ID,
                                                         "client_secret": CLIENT_SECRET}}))
        report.step("Bắt được client tạo nhầm loại Web application",
                    web.get("error") == "wrong_client_type:web",
                    web.get("error", ""))

        # 7. The consent link must ask for offline access, or there is no refresh token.
        started = run_cli("google_setup.py", "--creds-dir", str(creds), "start", env=env)
        url = started.get("auth_url", "")
        report.step("Link cấp quyền xin đúng quyền (offline + PKCE)",
                    all(bit in url for bit in ("access_type=offline", "prompt=consent",
                                               "code_challenge_method=S256")),
                    f"scope_set={started.get('scope_set')}")

        # 8. The whole point: the user pastes back the address bar of an error page.
        pending = goauth.read_pending(creds)
        pasted = (f"http://localhost:8765/?state={pending['state']}"
                  "&code=4%2F0AeanS0selftest&scope=https%3A%2F%2Fwww.googleapis.com"
                  "%2Fauth%2Fdrive.file")
        with StubGoogle("ok") as stub:
            code, state = goauth.extract_code(pasted)
            token_data = goauth.exchange_code(creds, code, pending)
            client_section = goauth.read_client_json(creds)["installed"]
            goauth.write_token(creds, token_data, client_section, pending["scopes"])
            account = goauth.whoami(token_data["access_token"])
            sent = stub.last_token_request
        report.step("Đổi mã lấy token từ đường link người dùng dán",
                    state == pending["state"] and token_data.get("refresh_token"),
                    f"account={account}")
        report.step(
            "Gửi lên Google đúng tham số (PKCE verifier + redirect_uri khớp)",
            sent.get("code_verifier") == [pending["code_verifier"]]
            and sent.get("redirect_uri") == [pending["redirect_uri"]]
            and sent.get("grant_type") == ["authorization_code"],
            f"fields={sorted(sent)}")
        report.step("Xoá phiên cấp quyền sau khi dùng (không tái sử dụng)",
                    not (creds / goauth.PENDING_FILE).exists(), "")

        # 9. The token file is only useful if doc-convert's library can read it.
        report.step(*token_readable(creds))

        # 10. A code that expired must produce the "ask for a new link" advice, not a stack trace.
        goauth.build_auth_url(creds, "minimal", 8765)
        stale = goauth.read_pending(creds)
        with StubGoogle("invalid_grant"):
            expired = run_finish_inprocess(creds, stale)
        report.step("Mã hết hạn được báo bằng lời sửa được, không phải lỗi kỹ thuật",
                    expired["error"].startswith("token_exchange_failed:invalid_grant")
                    and "`start` again" in expired["next_action"],
                    expired["next_action"][:90])

        # 11. A grant without a refresh token must fail loudly instead of dying in an hour.
        goauth.build_auth_url(creds, "minimal", 8765)
        pending2 = goauth.read_pending(creds)
        with StubGoogle("no_refresh"):
            silent = run_finish_inprocess(creds, pending2)
        report.step("Token không kèm refresh token bị coi là thất bại",
                    silent["error"] == "no_refresh_token",
                    silent["error"])

        # 12. And finally the state the user is told about at the end.
        final = run_cli("check_setup.py", "--creds-dir", str(creds), env=env)
        report.step("Trạng thái cuối: Morning Report chạy được, Google đã nối",
                    final["ready"]["morning_report"] and final["google"]["status"] == "ok",
                    f"ready={final['ready']}")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(creds, ignore_errors=True)
    return report


def run_finish_inprocess(creds: Path, pending: dict) -> dict:
    """Drive google_setup.cmd_finish against the stub, the way the CLI would."""
    import google_setup  # noqa: PLC0415 - imported late so the stub patch is in place

    class Args:
        creds_dir = str(creds)
        redirect_url = f"http://localhost:8765/?state={pending['state']}&code=4%2Fstub"

    return google_setup.cmd_finish(Args())


def token_readable(creds: Path) -> tuple[str, bool, str]:
    """Load token.json exactly as doc-convert does, if the Google libraries are here."""
    name = "token.json đọc được bằng chính thư viện doc-convert dùng"
    try:
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
    except ImportError:
        return (name, True, "bỏ qua: chưa cài google-auth trên máy này")
    try:
        creds_obj = Credentials.from_authorized_user_file(
            str(creds / "token.json"), [goauth.SCOPE_DRIVE_FILE])
    except Exception as err:  # noqa: BLE001 - the failure text is the finding
        return (name, False, str(err))
    return (name, bool(creds_obj.refresh_token and creds_obj.client_id), "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rehearse the guided-setup flow offline")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    report = rehearse()
    if args.json:
        print(json.dumps({"ok": not report.failed, "steps": report.steps},
                         ensure_ascii=False, indent=2))
    else:
        print("Diễn tập luồng cài đặt qua chat (không gọi Google thật, không đụng bản cài đang chạy)\n")
        for step in report.steps:
            mark = "PASS" if step["ok"] else "FAIL"
            line = f"  [{mark}] {step['step']}"
            print(f"{line}\n         {step['detail']}" if step["detail"] else line)
        print()
        if report.failed:
            print(f"{len(report.failed)} bước HỎNG — luồng cài đặt sẽ vấp ở đúng chỗ đó.")
        else:
            print("Toàn bộ luồng chạy trơn. Còn lại phải kiểm tay 1 lần với Google thật:")
            print("  docs/google-oauth-setup.vi.md, mục 'Kiểm thử với Google thật'.")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
