"""Token exchange against a local stand-in for Google.

The unit tests next door cover everything up to the network call. These cover the call
itself: what we put on the wire, how each failure comes back, and whether the token file
we write is the one google-auth expects to read. The stub lives in scripts/selftest.py so
the rehearsal an operator runs and the tests CI runs exercise the same fake.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from helpers import google_chat_oauth as goauth  # noqa: E402
from selftest import CLIENT_ID, CLIENT_SECRET, FAKE_ACCOUNT, StubGoogle  # noqa: E402

import google_setup  # noqa: E402

PASS = FAIL = 0
_KEEP = []


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


def prepared_creds():
    """A credentials dir with a client stored and an authorization in flight."""
    d = tempfile.TemporaryDirectory()
    _KEEP.append(d)
    creds = Path(d.name)
    goauth.write_client_json(creds, goauth.client_json_from_pair(CLIENT_ID, CLIENT_SECRET))
    goauth.build_auth_url(creds, "minimal", 8765)
    return creds, goauth.read_pending(creds)


def finish(creds, pasted):
    class Args:
        creds_dir = str(creds)
        redirect_url = pasted

    return google_setup.cmd_finish(Args())


def test_exchange_sends_the_verifier_and_stores_a_refresh_token():
    creds, pending = prepared_creds()
    with StubGoogle("ok") as stub:
        result = finish(creds, f"http://localhost:8765/?state={pending['state']}&code=4%2Fabc")
    assert result["success"] is True, result
    assert stub.last_token_request["code"] == ["4/abc"], stub.last_token_request
    assert stub.last_token_request["code_verifier"] == [pending["code_verifier"]]
    assert stub.last_token_request["client_secret"] == [CLIENT_SECRET]
    stored = json.loads((creds / "token.json").read_text(encoding="utf-8"))
    assert stored["refresh_token"] == "stub-refresh-token"


def test_finish_reports_the_connected_account_so_the_user_can_confirm_it():
    creds, pending = prepared_creds()
    with StubGoogle("ok"):
        result = finish(creds, f"http://localhost:8765/?state={pending['state']}&code=4%2Fabc")
    assert result["account"] == FAKE_ACCOUNT, result
    assert FAKE_ACCOUNT in result["next_action"]


def test_a_grant_without_a_refresh_token_is_a_failure_not_a_success():
    # It would work for an hour and then lock the bot out with no visible cause.
    creds, pending = prepared_creds()
    with StubGoogle("no_refresh"):
        result = finish(creds, f"http://localhost:8765/?state={pending['state']}&code=4%2Fabc")
    assert result["success"] is False
    assert result["error"] == "no_refresh_token"
    assert "myaccount.google.com/permissions" in result["next_action"]
    assert not (creds / "token.json").exists(), "a token with no refresh must not be stored"


def test_an_expired_code_is_explained_as_a_fresh_link_not_a_stack_trace():
    creds, pending = prepared_creds()
    with StubGoogle("invalid_grant"):
        result = finish(creds, f"http://localhost:8765/?state={pending['state']}&code=4%2Fold")
    assert result["error"].startswith("token_exchange_failed:invalid_grant"), result
    assert "`start` again" in result["next_action"]


def test_a_link_from_an_older_attempt_is_refused():
    creds, _ = prepared_creds()
    result = finish(creds, "http://localhost:8765/?state=someone-elses-state&code=4%2Fabc")
    assert result["error"] == "state_mismatch", result
    assert not (creds / "token.json").exists()


def test_the_pending_authorization_survives_a_failed_attempt():
    # The user gets a second try at pasting without redoing the consent screen.
    creds, pending = prepared_creds()
    finish(creds, "http://localhost:8765/?state=wrong&code=4%2Fabc")
    assert (creds / goauth.PENDING_FILE).exists()
    with StubGoogle("ok"):
        result = finish(creds, f"http://localhost:8765/?state={pending['state']}&code=4%2Fabc")
    assert result["success"] is True


def test_the_written_token_loads_with_google_auth():
    creds, pending = prepared_creds()
    with StubGoogle("ok"):
        finish(creds, f"http://localhost:8765/?state={pending['state']}&code=4%2Fabc")
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        return  # library not installed here; the deployment target has it
    loaded = Credentials.from_authorized_user_file(
        str(creds / "token.json"), [goauth.SCOPE_DRIVE_FILE])
    assert loaded.refresh_token == "stub-refresh-token"
    assert loaded.client_id == CLIENT_ID
    assert loaded.expiry is not None


def test_finish_reads_the_pasted_url_from_stdin_when_no_flag_is_given():
    # Redirect URLs are full of & and ?; a heredoc on stdin keeps the shell out of it.
    creds, pending = prepared_creds()

    class Args:
        creds_dir = str(creds)
        redirect_url = None

    import io

    saved = sys.stdin
    sys.stdin = io.StringIO(f"http://localhost:8765/?state={pending['state']}&code=4%2Fabc")
    try:
        with StubGoogle("ok"):
            result = google_setup.cmd_finish(Args())
    finally:
        sys.stdin = saved
    assert result["success"] is True, result


# -- Run --
for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
