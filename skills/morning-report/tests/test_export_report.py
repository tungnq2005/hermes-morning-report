"""Tests for export_report.py — the Morning Report -> doc-convert bridge.

doc-convert itself is stubbed: these tests are about resolving which stored report
the user meant, not about Google. The stub records how it was called, which is how
the "do not create a second file in the user's Drive" rule is proven.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from export_report import (  # noqa: E402
    classify_failure,
    describe_run,
    export_run,
    find_convert_script,
    list_runs,
    resolve_run,
)
from helpers.history import load_manifest  # noqa: E402

EXPORT_CLI = SCRIPTS / "export_report.py"

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


# ── Fixtures ───────────────────────────────────────────────────────────
FAKE_CONVERT = '''
import json, os, sys

args = sys.argv[1:]
log = os.environ.get("FAKE_CONVERT_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args) + "\\n")

mode = os.environ.get("FAKE_CONVERT_MODE", "ok")
title = args[args.index("--title") + 1] if "--title" in args else ""
run_dir = os.path.join(os.path.dirname(log or "."), "docrun")
os.makedirs(run_dir, exist_ok=True)
pdf = os.path.join(run_dir, "report.pdf")
open(pdf, "wb").write(b"%PDF-1.4 fake")

if mode == "local":
    out = {"success": True, "title": title, "render_engine": "local", "output": pdf,
           "warnings": ["google_unauthorized:rendered_locally"]}
elif mode == "unauthorized":
    out = {"success": False, "error": "Chưa kết nối Google. Kết nối ngay trong chat.",
           "warnings": []}
elif mode == "boom":
    out = {"success": False, "error": "Input file not found: nope.md", "warnings": []}
else:
    out = {"success": True, "title": title, "render_engine": "google",
           "google_url": "https://docs.google.com/document/d/FAKE123/edit",
           "google_id": "FAKE123", "output": pdf, "run_dir": run_dir, "warnings": []}

print(json.dumps(out, ensure_ascii=False))
sys.exit(0 if out["success"] else 1)
'''


def make_convert_stub(tmp: Path, mode: str = "ok") -> tuple[Path, Path]:
    script = tmp / "fake_convert.py"
    script.write_text(FAKE_CONVERT, encoding="utf-8")
    log = tmp / "convert-calls.log"
    os.environ["FAKE_CONVERT_LOG"] = str(log)
    os.environ["FAKE_CONVERT_MODE"] = mode
    return script, log


def make_run(history: Path, date: str, run_id: str, *, topic: str | None = None,
             title: str = "Bản tin sáng", with_report: bool = True) -> Path:
    run_dir = history / date / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if with_report:
        (run_dir / "report.md").write_text(f"# {title}\n\nNội dung.\n", encoding="utf-8")
    manifest = {"run_id": run_id, "created_at": f"{date}T00:00:00Z",
                "report": {"status": "validated", "file": "report.md"},
                "audio": {"status": "disabled", "file": None}}
    if topic is not None:
        manifest["topic"] = topic
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return run_dir


def call_count(log: Path) -> int:
    if not log.exists():
        return 0
    return len([line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()])


# ── Resolving which report the user meant ──────────────────────────────
def test_list_runs_newest_first():
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        make_run(history, "2026-08-18", "080000", topic="AI")
        make_run(history, "2026-08-19", "080000", topic="Crypto")
        make_run(history, "2026-08-19", "173000", topic="Gold")
        runs = list_runs(history)
        assert [r["topic"] for r in runs] == ["Gold", "Crypto", "AI"], runs


def test_list_runs_skips_runs_without_a_report():
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        make_run(history, "2026-08-19", "080000", topic="Crypto")
        make_run(history, "2026-08-19", "090000", topic="Failed", with_report=False)
        runs = list_runs(history)
        assert [r["topic"] for r in runs] == ["Crypto"], runs


def test_describe_run_reads_title_and_time():
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        run_dir = make_run(history, "2026-08-19", "173045", topic="Gold", title="Giá vàng 19/8")
        info = describe_run(run_dir)
        assert info["title"] == "Giá vàng 19/8", info
        assert info["time"] == "17:30", info
        assert info["date"] == "2026-08-19"


def test_topic_match_falls_back_to_title_for_legacy_runs():
    # Runs created before the manifest carried a topic must still be findable.
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        make_run(history, "2026-08-19", "080000", topic=None, title="Bản tin crypto 19/8")
        runs = list_runs(history)
        run, _ = resolve_run(runs, topic="crypto")
        assert run is not None and run["title"] == "Bản tin crypto 19/8"


def test_topic_match_is_case_insensitive_and_partial():
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        make_run(history, "2026-08-19", "080000", topic="Giá vàng thế giới")
        runs = list_runs(history)
        run, _ = resolve_run(runs, topic="GIÁ VÀNG")
        assert run is not None


def test_date_filter_and_no_match():
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        make_run(history, "2026-08-18", "080000", topic="AI")
        make_run(history, "2026-08-19", "080000", topic="Crypto")
        runs = list_runs(history)
        run, _ = resolve_run(runs, date="2026-08-18")
        assert run["topic"] == "AI"
        missing, candidates = resolve_run(runs, topic="weather")
        assert missing is None and candidates == []


# ── Exporting ──────────────────────────────────────────────────────────
def test_export_returns_google_url_and_records_it():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, _log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        result = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        assert result["success"] and result["reused"] is False, result
        assert result["google_url"].startswith("https://docs.google.com/"), result
        recorded = load_manifest(run_dir)["exports"]
        assert recorded[0]["target"] == "gdoc" and recorded[0]["google_url"] == result["google_url"]


def test_file_only_target_does_not_promise_a_link():
    # md/docx/pdf come back without a google_url; the agent must be told to send the
    # file, not to paste a link that does not exist.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, _log = make_convert_stub(tmp_path, mode="local")
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        result = export_run(describe_run(run_dir), target="md", convert_script=script)
        assert result["success"] and not result["google_url"], result
        assert "google_url" not in result["next_action"], result["next_action"]
        assert "MEDIA:" in result["next_action"]


def test_export_passes_the_report_title_through():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Gold", title="Giá vàng 19/8")
        export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        args = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert "--title" in args and args[args.index("--title") + 1] == "Giá vàng 19/8", args
        assert args[args.index("--to") + 1] == "gdoc"


def test_image_queries_reach_doc_convert():
    # A Vietnamese report gets no pictures at all unless English queries are passed
    # through, which is exactly what the bridge forgot to do at first.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Giá vàng")
        export_run(describe_run(run_dir), target="gdoc", convert_script=script,
                   image_queries=["gold bars", "", "federal reserve building"])
        args = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        passed = [args[i + 1] for i, a in enumerate(args) if a == "--image-query"]
        assert passed == ["gold bars", "", "federal reserve building"], args


def test_no_auto_images_is_passed_through():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        export_run(describe_run(run_dir), target="gdoc", convert_script=script,
                   no_auto_images=True)
        args = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert "--no-auto-images" in args, args


def test_same_queries_reuse_but_different_queries_rebuild():
    # Reuse is about "you already asked for this"; different pictures are a
    # different document, so they must not silently return the old one.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        first = export_run(describe_run(run_dir), target="gdoc", convert_script=script,
                           image_queries=["bitcoin"])
        same = export_run(describe_run(run_dir), target="gdoc", convert_script=script,
                          image_queries=["bitcoin"])
        other = export_run(describe_run(run_dir), target="gdoc", convert_script=script,
                           image_queries=["stock market"])
        assert first["reused"] is False and same["reused"] is True
        assert other["reused"] is False
        assert call_count(log) == 2, "the unchanged request should not have run again"


def test_asking_twice_reuses_the_same_file():
    # The whole point of recording exports: a second ask must not put a duplicate
    # document in the user's Drive.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        first = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        second = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        assert second["reused"] is True, second
        assert second["google_url"] == first["google_url"]
        assert call_count(log) == 1, "doc-convert ran twice for the same report"


def test_again_forces_a_new_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        again = export_run(describe_run(run_dir), target="gdoc", again=True, convert_script=script)
        assert again["reused"] is False and call_count(log) == 2


def test_a_different_target_is_its_own_export():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        slides = export_run(describe_run(run_dir), target="gslides", convert_script=script)
        assert slides["reused"] is False and call_count(log) == 2
        targets = {e["target"] for e in load_manifest(run_dir)["exports"]}
        assert targets == {"gdoc", "gslides"}, targets


def test_local_render_is_reported_as_not_connected_not_as_success():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, _log = make_convert_stub(tmp_path, mode="local")
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        result = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        assert result["success"] is False and result["error"] == "rendered_locally", result
        assert "guided-setup" in result["next_action"]
        assert "exports" not in load_manifest(run_dir), "a failed export must not be recorded"


def test_unauthorized_error_offers_the_in_chat_connection():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, _log = make_convert_stub(tmp_path, mode="unauthorized")
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        result = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        assert result["success"] is False
        assert "guided-setup" in result["next_action"] and "terminal" in result["next_action"]


def test_other_failures_are_reported_verbatim():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, _log = make_convert_stub(tmp_path, mode="boom")
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto")
        result = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        assert result["success"] is False
        assert "Input file not found" in result["next_action"], result["next_action"]


def test_missing_report_file_fails_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, _log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        run_dir = make_run(history, "2026-08-19", "080000", topic="Crypto", with_report=False)
        result = export_run(describe_run(run_dir), target="gdoc", convert_script=script)
        assert result["success"] is False and result["error"] == "report_missing"


def test_classify_failure_separates_google_from_real_errors():
    assert classify_failure({"error": "Chưa kết nối Google."}) == "google_unauthorized"
    assert classify_failure({"warnings": ["google_unauthorized:rendered_locally"]}) == "google_unauthorized"
    assert classify_failure({"error": "soffice crashed"}) == "convert_failed"


def test_find_convert_script_prefers_the_env_override():
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "doc-convert" / "scripts"
        fake.mkdir(parents=True)
        (fake / "convert.py").write_text("", encoding="utf-8")
        os.environ["DOC_CONVERT_DIR"] = str(fake.parent)
        try:
            assert find_convert_script() == fake / "convert.py"
        finally:
            del os.environ["DOC_CONVERT_DIR"]


def test_find_convert_script_finds_the_repo_sibling():
    # No env override: the real repo layout (skills/doc-convert) must be enough.
    os.environ.pop("DOC_CONVERT_DIR", None)
    found = find_convert_script()
    assert found is not None and found.name == "convert.py", found


# ── CLI ────────────────────────────────────────────────────────────────
def run_cli(args, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    proc = subprocess.run([sys.executable, str(EXPORT_CLI), *args],
                          capture_output=True, text=True, env=env)
    return json.loads(proc.stdout)


def test_cli_list_reports_topic_and_date():
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        make_run(history, "2026-08-19", "080000", topic="Crypto")
        out = run_cli(["--list", "--history-dir", str(history)])
        assert out["success"] and out["reports"][0]["topic"] == "Crypto"
        assert "next_action" in out


def test_cli_with_no_history_says_there_is_nothing_to_export():
    with tempfile.TemporaryDirectory() as tmp:
        out = run_cli(["--history-dir", str(Path(tmp) / "history")])
        assert out["success"] is False and out["error"] == "no_runs"
        assert "Run Report" in out["next_action"]


def test_cli_exports_the_newest_report_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script, log = make_convert_stub(tmp_path)
        history = tmp_path / "history"
        make_run(history, "2026-08-18", "080000", topic="AI")
        make_run(history, "2026-08-19", "080000", topic="Crypto")
        out = run_cli(["--history-dir", str(history), "--convert-script", str(script)],
                      {"FAKE_CONVERT_LOG": str(log), "FAKE_CONVERT_MODE": "ok"})
        assert out["success"] and out["topic"] == "Crypto", out
        assert out["google_url"].startswith("https://docs.google.com/")


def test_cli_reports_an_unknown_run_dir_without_crashing():
    with tempfile.TemporaryDirectory() as tmp:
        out = run_cli(["--run-dir", str(Path(tmp) / "gone")])
        assert out["success"] is False and out["error"] == "run_dir_not_found"


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
