"""Report style normalization for Morning Report helpers."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

CANONICAL_STYLES = ("concise", "deep_analysis", "opportunities_risks")

STYLE_ALIASES = {
    "concise": "concise",
    "short": "concise",
    "brief": "concise",
    "quick": "concise",
    "summary": "concise",
    "deep analysis": "deep_analysis",
    "detailed": "deep_analysis",
    "full": "deep_analysis",
    "analyst": "deep_analysis",
    "explain more": "deep_analysis",
    "opportunities risks": "opportunities_risks",
    "risks opportunities": "opportunities_risks",
    "opportunity risk": "opportunities_risks",
    "opportunity risks": "opportunities_risks",
    "opportunities risk": "opportunities_risks",
    "risks": "opportunities_risks",
    "risk": "opportunities_risks",
    "opportunity": "opportunities_risks",
    "opportunities": "opportunities_risks",
    "strategy": "opportunities_risks",
    "decision": "opportunities_risks",
    "action oriented": "opportunities_risks",
}


def style_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip())
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[/|+]", " ", text)
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_report_style(value: str) -> str:
    key = style_key(value)
    if key in STYLE_ALIASES:
        return STYLE_ALIASES[key]
    raise ValueError(
        "unsupported_report_style: "
        f"{value!r}. Use one of: {', '.join(CANONICAL_STYLES)}"
    )


def suggest_report_style(value: str) -> dict[str, str | bool]:
    """Return a safe style suggestion for conversational confirmation.

    Unknown style wording falls back to concise, but callers must confirm the
    suggestion with the user before saving it.
    """

    try:
        canonical = normalize_report_style(value)
        return {
            "raw": value,
            "canonical": canonical,
            "recognized": True,
            "fallback_used": False,
            "needs_confirmation": False,
        }
    except ValueError:
        return {
            "raw": value,
            "canonical": "concise",
            "recognized": False,
            "fallback_used": True,
            "needs_confirmation": True,
            "reason": "unrecognized_report_style_default_to_concise",
        }


def report_style_info(value: str) -> dict[str, str | bool]:
    try:
        canonical = normalize_report_style(value)
        return {
            "raw": value,
            "canonical": canonical,
            "valid": True,
            "is_canonical": value.strip() == canonical,
        }
    except ValueError as exc:
        return {
            "raw": value,
            "canonical": "",
            "valid": False,
            "is_canonical": False,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize or suggest Morning Report style")
    parser.add_argument("value", nargs="+", help="Report style text")
    parser.add_argument("--suggest", action="store_true", help="Fallback unclear styles to concise for confirmation")
    args = parser.parse_args()

    value = " ".join(args.value)
    if args.suggest:
        print(json.dumps(suggest_report_style(value), ensure_ascii=False, indent=2))
        return 0

    info = report_style_info(value)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
