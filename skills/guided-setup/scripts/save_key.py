#!/usr/bin/env python3
"""Take a key the user pasted into chat, prove it works, and store it. Prints JSON.

The value arrives as a chat message, so it is cleaned before anything else touches it
(see helpers/envfile.clean_pasted). It is then verified against the provider and only
written to ~/.hermes/.env if the provider accepted it -- a key that is stored but wrong
turns into a silent failure at delivery time, which is exactly what this flow exists to
prevent.

The key itself is never printed back: chat history is not a place for secrets, and the
masked fingerprint is enough for the user to tell two keys apart.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import envfile, keyspec  # noqa: E402

# Problems that mean "this is not a key at all" -- saving would guarantee a later failure.
FATAL_PROBLEMS = {"empty", "placeholder", "looks_like_url", "looks_like_email", "contains_spaces"}

PROBLEM_TEXT = {
    "empty": "the message contained no key",
    "placeholder": "that is a placeholder, not a real key",
    "looks_like_url": "that is a web address — the key is the string shown ON that page",
    "looks_like_email": "that is an email address, not an API key",
    "contains_spaces": "the value contains spaces, so part of a sentence was copied too",
    "too_short": "the value is shorter than any real key from this provider",
}


def save(name: str, raw_value: str, do_verify: bool, force: bool) -> dict:
    key_id = keyspec.resolve_id(name)
    if not key_id:
        return {"success": False, "error": "unknown_key",
                "known_keys": sorted(keyspec.KEY_SPECS),
                "next_action": "Stop. The key name is not one this skill manages. "
                               "Use one of known_keys."}
    spec = keyspec.KEY_SPECS[key_id]
    value, problems = envfile.clean_pasted(raw_value)
    fatal = sorted(FATAL_PROBLEMS & set(problems))

    result = {
        "success": False,
        "key": key_id,
        "env": spec["env"],
        "masked": envfile.mask(value),
        "saved": False,
        "problems": problems,
        "problem_text": [PROBLEM_TEXT.get(problem, problem) for problem in problems],
    }

    if fatal and not force:
        result["next_action"] = (
            "Do not save. Reply in the user's language: "
            f"{'; '.join(PROBLEM_TEXT.get(problem, problem) for problem in fatal)}. "
            f"Point the user back to {spec['console']} and ask them to paste just the key.")
        return result

    if spec["prefix_hint"] and not value.startswith(spec["prefix_hint"]):
        # A hint, not a rule: providers do rotate their prefixes, and refusing a working
        # key because of a format guess is worse than saving one with a warning.
        result.setdefault("warnings", []).append(
            f"unexpected_prefix:keys from this provider usually start with "
            f"{spec['prefix_hint']!r}")

    if do_verify:
        check = keyspec.verify(key_id, value)
        result["verify"] = check
        if check["state"] == "rejected" and not force:
            result["next_action"] = (
                "Do not save. Reply in the user's language: the provider rejected this key "
                f"(HTTP {check['http_status']}). Common causes: the key was copied only "
                "partly, it was deleted in the console, or the free quota ran out. Ask the "
                f"user to create a new key at {spec['console']} and paste it again.")
            return result
        if check["state"] == "unverified":
            result.setdefault("warnings", []).append(
                "not_verified:the provider could not be reached, so the key is saved "
                "unproven — re-run check_setup.py --verify later")

    path = envfile.set_env(spec["env"], value)
    result["success"] = True
    result["saved"] = True
    result["env_file"] = str(path)
    verified = result.get("verify", {}).get("state") == "verified"
    result["next_action"] = (
        "Reply in the user's language: the key was saved"
        + (" and confirmed working with the provider" if verified else "")
        + ". Never repeat the key back to the user — refer to it by the masked value. "
        "Then run check_setup.py to see what is still missing and continue with the "
        "next item.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Save an API key pasted in chat")
    parser.add_argument("--name", required=True,
                        help="Key id (exa, firecrawl, brave) or env var name")
    parser.add_argument("--value", help="What the user pasted; omit to read stdin")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip the live provider check (offline install)")
    parser.add_argument("--force", action="store_true",
                        help="Save even if the value looks wrong or the provider rejected it")
    args = parser.parse_args()

    raw = args.value if args.value is not None else sys.stdin.read()
    result = save(args.name, raw, not args.no_verify, args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
