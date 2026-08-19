"""Tests for validate_report_text.py — style rules, structure checks."""

import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate import validate_report, STYLE_RULES

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


# ── Concise style rules ──
CONCISE = "# Test Report\n\n## Section A\n- bullet 1\n- bullet 2\n- bullet 3\n- bullet 4\n- bullet 5\n\n## Section B\n- item\n\n## Section C\n- item\n\n" + "content " * 390 + "\n[link](https://example.com/a)"

SHORT = "# Short\n\n## One\n- bullet\n\n[link](https://example.com)"

DEEP_PASS = "# Deep\n\n## A\n### Sub\n- bullet 1\n- bullet 2\n- bullet 3\n- bullet 4\n- bullet 5\n- bullet 6\n\n## B\n- x\n\n## C\n- x\n\n## D\n- x\n\n" + "analysis " * 890 + "\n[link](https://example.com/x)"


def test_concise_pass():
    r = validate_report(CONCISE, "concise")
    assert r["ok"], f"expected ok, got {r['issues']}"

def test_too_short():
    r = validate_report(SHORT, "concise")
    assert r["issues"], "expected issues for short report"

def test_empty():
    r = validate_report("", "concise")
    assert not r["ok"]

def test_missing_title():
    r = validate_report("no title here\n\n## Section\n- bullet\n\n[link](https://x.com)", "concise")
    assert any(i["code"] == "missing_title" for i in r["issues"])

def test_decorative_emoji():
    r = validate_report("# 🏆 Test Report\n\n## S\n- bullet 1\n- bullet 2\n- bullet 3\n- bullet 4\n- bullet 5\n\n## T\n- x\n\n## U\n- x\n\n[link](https://x.com)", "concise")
    assert any(i["code"] == "decorative_symbol_in_title" for i in r["issues"])

def test_missing_links():
    r = validate_report("# Test\n\n## A\n- bullet 1\n- bullet 2\n- bullet 3\n- bullet 4\n- bullet 5\n\n## B\n- x\n\n## C\n- x\n\n" + "content " * 390, "concise")
    assert any(i["code"] == "missing_evidence_links" for i in r["issues"])

def test_deep_subsections():
    r = validate_report("# Deep\n\n## A\n- bullet 1\n- bullet 2\n- bullet 3\n- bullet 4\n- bullet 5\n- bullet 6\n\n## B\n- x\n\n## C\n- x\n\n## D\n- x\n\n" + "analysis " * 890 + "\n[link](https://x.com)", "deep_analysis")
    assert any(i["code"] == "missing_subsections" for i in r["issues"])

def test_deep_pass():
    r = validate_report(DEEP_PASS, "deep_analysis")
    assert r["ok"], f"expected ok, got {r['issues']}"

# ── Heading language ──
# The style guide already said "headings in the report language" and the model still
# shipped English ones over a Vietnamese report, twice in the same run directory.
VI_BODY = "\n\n## Điểm chính\n- một\n- hai\n- ba\n- bốn\n- năm\n\n## Cần theo dõi\n- x\n\n## Giới hạn\n- x\n\n" + "nội dung " * 390 + "\n[nguồn](https://example.com/a)"

def test_english_headings_rejected_on_a_vietnamese_report():
    text = "# Bản tin sáng\n\n## Snapshot\n- một\n- hai\n- ba\n- bốn\n- năm\n\n## Key updates\n- x\n\n## Limitations\n- x\n\n" + "nội dung " * 390 + "\n[nguồn](https://example.com/a)"
    r = validate_report(text, "concise", "Vietnamese")
    assert any(i["code"] == "heading_language" for i in r["issues"]), r["issues"]

def test_vietnamese_headings_accepted():
    r = validate_report("# Bản tin sáng" + VI_BODY, "concise", "Vietnamese")
    assert not any(i["code"] == "heading_language" for i in r["issues"]), r["issues"]

def test_english_headings_fine_when_the_report_is_english():
    text = "# Morning Brief\n\n## Snapshot\n- a\n- b\n- c\n- d\n- e\n\n## Key updates\n- x\n\n## Limitations\n- x\n\n" + "content " * 390 + "\n[src](https://example.com/a)"
    assert not any(i["code"] == "heading_language" for i in validate_report(text, "concise", "English")["issues"])

def test_heading_check_skipped_without_a_language():
    text = "# Bản tin sáng\n\n## Snapshot\n- một\n- hai\n- ba\n- bốn\n- năm\n\n## Key updates\n- x\n\n## Giới hạn\n- x\n\n" + "nội dung " * 390 + "\n[nguồn](https://example.com/a)"
    assert not any(i["code"] == "heading_language" for i in validate_report(text, "concise")["issues"])


# ── Percentage arithmetic ──
# A real report said Bitcoin at $64.3K was "thấp hơn ~45%" than $93K. It is 31%.
def test_percentage_that_contradicts_the_figures_beside_it():
    text = ("# Bản tin sáng\n\n## Điểm chính\n"
            "- **Bitcoin quanh $64.3K**: vẫn thấp hơn ~45% so với mức mở cửa tháng 1 (~$93K).\n"
            "- hai\n- ba\n- bốn\n- năm\n\n## Cần theo dõi\n- x\n\n## Giới hạn\n- x\n\n"
            + "nội dung " * 390 + "\n[nguồn](https://example.com/a)")
    issues = validate_report(text, "concise", "Vietnamese")["issues"]
    hit = [i for i in issues if i["code"] == "percentage_mismatch"]
    assert hit, issues
    assert "31%" in hit[0]["message"], hit[0]["message"]

def test_percentage_that_matches_is_left_alone():
    text = ("# Bản tin sáng\n\n## Điểm chính\n"
            "- **Bitcoin quanh $64.3K**: thấp hơn ~31% so với mức mở cửa tháng 1 (~$93K).\n"
            "- hai\n- ba\n- bốn\n- năm\n\n## Cần theo dõi\n- x\n\n## Giới hạn\n- x\n\n"
            + "nội dung " * 390 + "\n[nguồn](https://example.com/a)")
    assert not [i for i in validate_report(text, "concise", "Vietnamese")["issues"]
                if i["code"] == "percentage_mismatch"]

def test_a_month_number_is_not_mistaken_for_a_price():
    """An early version read the '1' out of 'tháng 1' and reported a 6,429,900% error."""
    text = ("# Bản tin sáng\n\n## Điểm chính\n"
            "- **Bitcoin quanh $64.3K**: giảm 5% trong tháng 1 theo dữ liệu on-chain.\n"
            "- hai\n- ba\n- bốn\n- năm\n\n## Cần theo dõi\n- x\n\n## Giới hạn\n- x\n\n"
            + "nội dung " * 390 + "\n[nguồn](https://example.com/a)")
    assert not [i for i in validate_report(text, "concise", "Vietnamese")["issues"]
                if i["code"] == "percentage_mismatch"]


def test_style_rules_loaded():
    assert "concise" in STYLE_RULES
    assert STYLE_RULES["concise"]["min_words"] == 400
    assert STYLE_RULES["concise"]["max_words"] == 600
    assert STYLE_RULES["deep_analysis"]["min_words"] == 900


# ── Run ──
for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
