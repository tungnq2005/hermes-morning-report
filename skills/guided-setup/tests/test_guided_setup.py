"""Tests for guided-setup: pasted-value hygiene, .env writes, status, Google chat OAuth."""

import base64
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from helpers import envfile, keyspec  # noqa: E402
from helpers import google_chat_oauth as goauth  # noqa: E402

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


def tmpdir():
    d = tempfile.TemporaryDirectory()
    _KEEP.append(d)
    return Path(d.name)


_KEEP = []

CLIENT_JSON = {
    "installed": {
        "client_id": "1234-abc.apps.googleusercontent.com",
        "client_secret": "GOCSPX-secret",
        "auth_uri": goauth.AUTH_ENDPOINT,
        "token_uri": goauth.TOKEN_ENDPOINT,
    }
}


# -- clean_pasted -------------------------------------------------------
def test_clean_strips_quotes_and_labels():
    assert envfile.clean_pasted('"abcdefgh1234"')[0] == "abcdefgh1234"
    assert envfile.clean_pasted("EXA_API_KEY=abcdefgh1234")[0] == "abcdefgh1234"
    assert envfile.clean_pasted("API key: fc-abcdefgh")[0] == "fc-abcdefgh"
    assert envfile.clean_pasted("`fc-abcdefgh1234`")[0] == "fc-abcdefgh1234"


def test_clean_takes_the_key_line_out_of_a_multiline_paste():
    value, problems = envfile.clean_pasted("Đây là key của mình nhé:\n\nfc-abcdefgh1234\n")
    assert value == "fc-abcdefgh1234", value
    assert problems == [], problems


def test_clean_flags_a_url_instead_of_a_key():
    value, problems = envfile.clean_pasted("https://dashboard.exa.ai/api-keys")
    assert "looks_like_url" in problems
    assert value  # still returned so the caller can show what was received


def test_clean_flags_email_placeholder_and_short_values():
    assert "looks_like_email" in envfile.clean_pasted("someone@example.com")[1]
    assert "placeholder" in envfile.clean_pasted("your_key")[1]
    assert "too_short" in envfile.clean_pasted("abc123")[1]
    assert envfile.clean_pasted("   ")[1] == ["empty"]


def test_clean_keeps_trailing_equals_of_base64_keys():
    # Stripping "=" would quietly corrupt base64-shaped keys.
    assert envfile.clean_pasted("YWJjZGVmZ2g=")[0] == "YWJjZGVmZ2g="


def test_mask_never_reveals_the_middle():
    masked = envfile.mask("abcd12345678wxyz")
    assert masked.startswith("abcd") and masked.endswith("(16 chars)")
    assert "12345678" not in masked


# -- .env writes --------------------------------------------------------
def test_set_env_appends_then_updates_in_place():
    path = tmpdir() / ".env"
    envfile.set_env("EXA_API_KEY", "one", path)
    envfile.set_env("FIRECRAWL_API_KEY", "two", path)
    envfile.set_env("EXA_API_KEY", "three", path)
    values = envfile.read_env(path)
    assert values["EXA_API_KEY"] == "three", values
    assert values["FIRECRAWL_API_KEY"] == "two", values
    assert path.read_text(encoding="utf-8").count("EXA_API_KEY=") == 1


def test_set_env_preserves_unrelated_lines_and_comments():
    path = tmpdir() / ".env"
    path.write_text("# comment\nTELEGRAM_BOT_TOKEN=abc\n", encoding="utf-8")
    envfile.set_env("EXA_API_KEY", "one", path)
    text = path.read_text(encoding="utf-8")
    assert "# comment" in text and "TELEGRAM_BOT_TOKEN=abc" in text
    assert envfile.read_env(path)["EXA_API_KEY"] == "one"


def test_set_env_locks_the_file_down():
    if os.name == "nt":
        return  # POSIX modes only; the deployment target is Linux
    path = tmpdir() / ".env"
    envfile.set_env("EXA_API_KEY", "one", path)
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_read_env_ignores_comments_and_missing_file():
    path = tmpdir() / ".env"
    assert envfile.read_env(path) == {}
    path.write_text("# nope\n\nA=1\nbroken line\nB=\"2\"\n", encoding="utf-8")
    assert envfile.read_env(path) == {"A": "1", "B": "2"}


# -- key registry -------------------------------------------------------
def test_resolve_id_accepts_both_id_and_env_name():
    assert keyspec.resolve_id("exa") == "exa"
    assert keyspec.resolve_id("EXA_API_KEY") == "exa"
    assert keyspec.resolve_id("BRAVE_SEARCH_API_KEY") == "brave"
    assert keyspec.resolve_id("nope") is None


def test_verdict_only_calls_auth_failures_invalid():
    assert keyspec._verdict(200, (200,))["state"] == "verified"
    assert keyspec._verdict(401, (200,))["state"] == "rejected"
    assert keyspec._verdict(403, (200,))["state"] == "rejected"
    # A 500 or a timeout says nothing about the key.
    assert keyspec._verdict(500, (200,))["state"] == "unverified"
    assert keyspec._verdict(0, (200,))["state"] == "unverified"


def test_brave_rate_limit_counts_as_a_working_key():
    assert keyspec._verdict(429, (200, 429))["state"] == "verified"


# -- save_key -----------------------------------------------------------
def test_save_key_refuses_a_url_and_writes_nothing():
    import save_key

    env = tmpdir() / ".env"
    os.environ["HERMES_HOME"] = str(env.parent)
    result = save_key.save("exa", "https://dashboard.exa.ai/api-keys", False, False)
    assert result["success"] is False
    assert result["saved"] is False
    assert not env.exists()


def test_save_key_stores_a_clean_value_without_echoing_it():
    import save_key

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    result = save_key.save("exa", "  my-exa-key-1234  ", False, False)
    assert result["success"] is True
    assert envfile.read_env(home / ".env")["EXA_API_KEY"] == "my-exa-key-1234"
    assert "my-exa-key-1234" not in json.dumps(result)


def test_save_key_force_overrides_a_refusal():
    import save_key

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    result = save_key.save("brave", "not a key", False, True)
    assert result["success"] is True
    assert envfile.read_env(home / ".env")["BRAVE_SEARCH_API_KEY"] == "not a key"


def test_save_key_warns_on_an_unexpected_prefix_but_still_saves():
    import save_key

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    result = save_key.save("firecrawl", "zz-abcdefgh1234", False, False)
    assert result["success"] is True
    assert any("unexpected_prefix" in w for w in result.get("warnings", []))


# -- check_setup --------------------------------------------------------
def test_check_setup_reports_missing_keys_and_the_next_step():
    import check_setup

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    envfile.set_env("BRAVE_SEARCH_API_KEY", "BSAxxxxxxxx", home / ".env")
    report = check_setup.build_report(False, str(tmpdir()))
    assert report["ready"]["morning_report"] is True  # Brave alone is enough to search
    assert "exa" in report["missing"] and "google" in report["missing"]
    assert report["next_step"] == "exa"
    assert any("firecrawl_missing" in w for w in report["warnings"])


def test_check_setup_treats_an_unreachable_provider_as_unproven_not_broken():
    import check_setup
    from helpers import keyspec as ks

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    envfile.set_env("EXA_API_KEY", "exa-key-1234", home / ".env")
    original = dict(ks.VERIFIERS)
    ks.VERIFIERS["exa"] = lambda value: {"ok": False, "state": "unverified", "http_status": 0}
    try:
        report = check_setup.build_report(True, str(tmpdir()))
    finally:
        ks.VERIFIERS.clear()
        ks.VERIFIERS.update(original)
    exa = next(k for k in report["keys"] if k["id"] == "exa")
    assert exa["status"] == "unverified"
    # The key may well be fine, so the report must not declare the report broken.
    assert report["ready"]["morning_report"] is True
    assert any("exa_unverified" in w for w in report["warnings"])


def test_check_setup_marks_a_rejected_key_invalid_and_blocks_the_report():
    import check_setup
    from helpers import keyspec as ks

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    envfile.set_env("EXA_API_KEY", "dead-key", home / ".env")
    original = dict(ks.VERIFIERS)
    ks.VERIFIERS["exa"] = lambda value: {"ok": False, "state": "rejected", "http_status": 401}
    try:
        report = check_setup.build_report(True, str(tmpdir()))
    finally:
        ks.VERIFIERS.clear()
        ks.VERIFIERS.update(original)
    exa = next(k for k in report["keys"] if k["id"] == "exa")
    assert exa["status"] == "invalid"
    assert report["ready"]["morning_report"] is False


def test_check_setup_never_prints_a_stored_key():
    import check_setup

    home = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    envfile.set_env("EXA_API_KEY", "supersecretvalue123", home / ".env")
    report = check_setup.build_report(False, str(tmpdir()))
    assert "supersecretvalue123" not in json.dumps(report)


def test_check_setup_sees_a_token_and_its_scopes():
    import check_setup

    home = tmpdir()
    creds = tmpdir()
    os.environ["HERMES_HOME"] = str(home)
    (creds / "client_secret.json").write_text(json.dumps(CLIENT_JSON), encoding="utf-8")
    (creds / "token.json").write_text(
        json.dumps({"scopes": [goauth.SCOPE_DRIVE_FILE, goauth.SCOPE_DRIVE_READONLY]}),
        encoding="utf-8")
    report = check_setup.build_report(False, str(creds))
    assert report["google"]["status"] == "ok"
    assert report["google"]["can_read_private_links"] is True
    assert "google" not in report["missing"]


# -- Google client parsing ---------------------------------------------
def test_parse_client_json_accepts_a_desktop_client():
    parsed = goauth.parse_client_json(json.dumps(CLIENT_JSON))
    assert parsed["installed"]["client_id"].endswith(".apps.googleusercontent.com")


def test_parse_client_json_tolerates_chat_noise_around_the_json():
    raw = "đây nhé:\n```\n" + json.dumps(CLIENT_JSON) + "\n```\ncảm ơn bạn"
    assert goauth.parse_client_json(raw)["installed"]["client_secret"] == "GOCSPX-secret"


def test_parse_client_json_rejects_a_web_client():
    try:
        goauth.parse_client_json(json.dumps({"web": CLIENT_JSON["installed"]}))
    except goauth.GoogleSetupError as err:
        assert str(err) == "wrong_client_type:web"
    else:
        raise AssertionError("a web client must be refused before it fails at consent")


def test_client_json_from_pair_checks_the_client_id_shape():
    built = goauth.client_json_from_pair("1234-abc.apps.googleusercontent.com", "s3cret")
    assert built["installed"]["token_uri"] == goauth.TOKEN_ENDPOINT
    try:
        goauth.client_json_from_pair("1234-abc", "s3cret")
    except goauth.GoogleSetupError as err:
        assert str(err) == "bad_client_id"
    else:
        raise AssertionError("a truncated client id must be refused")


# -- Google consent flow ------------------------------------------------
def test_build_auth_url_asks_for_offline_access_and_pkce():
    creds = tmpdir()
    goauth.write_client_json(creds, CLIENT_JSON)
    started = goauth.build_auth_url(creds, "minimal", 8765)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(started["auth_url"]).query)
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["redirect_uri"] == ["http://localhost:8765"]
    assert query["scope"] == [goauth.SCOPE_DRIVE_FILE]
    assert query["code_challenge_method"] == ["S256"]

    pending = json.loads((creds / goauth.PENDING_FILE).read_text(encoding="utf-8"))
    digest = hashlib.sha256(pending["code_verifier"].encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert query["code_challenge"] == [expected]
    assert query["state"] == [pending["state"]]


def test_private_links_scope_set_asks_for_readonly_too():
    creds = tmpdir()
    goauth.write_client_json(creds, CLIENT_JSON)
    started = goauth.build_auth_url(creds, "private-links", 8765)
    assert goauth.SCOPE_DRIVE_READONLY in started["scopes"]
    assert goauth.SCOPE_DRIVE_READONLY in urllib.parse.unquote(started["auth_url"])


def test_extract_code_reads_the_address_bar_paste():
    code, state = goauth.extract_code(
        "http://localhost:8765/?state=abc123&code=4%2F0AY0e-g7&scope=drive.file")
    assert code == "4/0AY0e-g7"
    assert state == "abc123"


def test_extract_code_accepts_a_bare_code_and_extra_words():
    assert goauth.extract_code("4/0AY0e-g7")[0] == "4/0AY0e-g7"
    assert goauth.extract_code(
        "đây bạn: http://localhost:8765/?code=4/xyz&state=s1")[0] == "4/xyz"


def test_extract_code_explains_a_denied_consent():
    try:
        goauth.extract_code("http://localhost:8765/?error=access_denied")
    except goauth.GoogleSetupError as err:
        assert str(err) == "consent_error:access_denied"
    else:
        raise AssertionError("a denied consent must not look like a missing code")


def test_extract_code_refuses_text_with_no_code():
    try:
        goauth.extract_code("mình bấm cho phép rồi nhưng trang báo lỗi")
    except goauth.GoogleSetupError as err:
        assert str(err) == "no_code_in_url"
    else:
        raise AssertionError("a chat message without a code must be refused")


def test_pending_authorization_expires():
    creds = tmpdir()
    goauth.write_client_json(creds, CLIENT_JSON)
    goauth.build_auth_url(creds, "minimal", 8765)
    path = creds / goauth.PENDING_FILE
    pending = json.loads(path.read_text(encoding="utf-8"))
    pending["created_at"] = int(time.time()) - goauth.PENDING_TTL_SECONDS - 1
    path.write_text(json.dumps(pending), encoding="utf-8")
    try:
        goauth.read_pending(creds)
    except goauth.GoogleSetupError as err:
        assert str(err) == "authorization_expired"
    else:
        raise AssertionError("a stale verifier must not be reused")


def test_write_token_matches_what_google_auth_reads_back():
    creds = tmpdir()
    goauth.write_client_json(creds, CLIENT_JSON)
    goauth.build_auth_url(creds, "minimal", 8765)
    path = goauth.write_token(
        creds,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3599,
         "scope": goauth.SCOPE_DRIVE_FILE},
        CLIENT_JSON["installed"], [goauth.SCOPE_DRIVE_FILE])
    stored = json.loads(path.read_text(encoding="utf-8"))
    # google.oauth2.credentials.Credentials.from_authorized_user_info requires these three.
    for field in ("refresh_token", "client_id", "client_secret"):
        assert stored.get(field), field
    assert stored["token_uri"] == goauth.TOKEN_ENDPOINT
    assert stored["scopes"] == [goauth.SCOPE_DRIVE_FILE]
    assert stored["expiry"].endswith("Z")
    # The half-finished authorization must not linger and be reused.
    assert not (creds / goauth.PENDING_FILE).exists()
    assert goauth.token_scopes(creds) == [goauth.SCOPE_DRIVE_FILE]


def test_credentials_dir_prefers_the_exported_environment():
    exported = tmpdir()
    env_only = tmpdir()
    (env_only / "token.json").write_text("{}", encoding="utf-8")
    os.environ["DOC_CONVERT_GCREDS_DIR"] = str(exported)
    try:
        assert goauth.resolve_creds_dir(None, str(env_only)) == exported
    finally:
        del os.environ["DOC_CONVERT_GCREDS_DIR"]
    # With nothing exported, an .env path that already holds credentials is honoured.
    assert goauth.resolve_creds_dir(None, str(env_only)) == env_only
    # An .env path with nothing in it is ignored in favour of doc-convert's own default.
    assert goauth.resolve_creds_dir(None, str(tmpdir())) == goauth.doc_convert_default_creds_dir()


def test_default_creds_dir_points_at_doc_convert():
    default = goauth.doc_convert_default_creds_dir()
    assert default.parts[-3:] == ("doc-convert", "state", "google-creds"), default


# -- Run --
for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
