#!/usr/bin/env bash
# Document-conversion add-on (skill D2, doc-convert) for macOS.
#
#   bash install-doc-addon.sh              standalone, re-runnable after a failure
#   bash install-doc-addon.sh --chained    called by install-mac.sh step 10
#
# Both skills are part of the standard handover — this lives in its own script for
# failure isolation, not because it is optional. The morning report needs only the
# Python that ships with macOS plus curl. Document conversion needs Homebrew, the
# Xcode command line tools, LibreOffice and 7 Python packages: four extra ways to
# fail. Separated, a LibreOffice problem cannot stop the morning report.
set -euo pipefail

CHAINED=false
[[ "${1:-}" == "--chained" ]] && CHAINED=true

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_DIR="$SRC_DIR/setup/lib"
HERMES_ENV_FILE="$HOME/.hermes/.env"
export HERMES_ENV_FILE
# shellcheck source=lib/wizard-prompts.sh
source "$LIB_DIR/wizard-prompts.sh"

D2_DEST="$HOME/.hermes/skills/doc-convert"
D1_DEST="$HOME/.hermes/skills/productivity/morning-report"
PIP_PACKAGES=(python-docx python-pptx pypdf google-api-python-client
              google-auth google-auth-oauthlib google-auth-httplib2)

# ── Which python does a skill script actually run under? ────────────────
# Not a question we may guess: the gateway's launchd plist puts
# <install>/venv/bin first on PATH, and skill docs call bare `python3`. So
# `python3` inside a skill IS the Hermes venv python — a separate venv would be
# invisible to the skill and the packages would look installed but never load.
# Source of truth, in order: the plist's VIRTUAL_ENV, then the known install path.
resolve_skill_python() {
    local plist="$HOME/Library/LaunchAgents/ai.hermes.gateway.plist" venv=""
    if [[ -f "$plist" ]]; then
        venv="$(sed -n '/<key>VIRTUAL_ENV<\/key>/{n;s/.*<string>\(.*\)<\/string>.*/\1/p;}' "$plist" | head -n 1)"
        if [[ -n "$venv" && -x "$venv/bin/python3" ]]; then
            printf '%s' "$venv/bin/python3"; return 0
        fi
    fi
    if [[ -x "$HOME/.hermes/hermes-agent/venv/bin/python3" ]]; then
        printf '%s' "$HOME/.hermes/hermes-agent/venv/bin/python3"; return 0
    fi
    command -v python3
}

step_check_d1() {
    say_step "Checking the morning report is installed first"
    if [[ -d "$D1_DEST" ]]; then
        say_ok "Morning report found."
    elif [[ "$CHAINED" == "true" ]]; then
        say_warn "Morning report not found — continuing anyway."
    else
        say_err "The morning report is not installed. Run setup/install-mac.sh first."
        exit 1
    fi
}

step_homebrew() {
    say_step "Checking Homebrew (needed for LibreOffice)"
    if command -v brew >/dev/null 2>&1; then
        say_ok "Homebrew found at $(brew --prefix)"
        return 0
    fi
    say "Homebrew is a standard installer for Mac software. LibreOffice needs it."
    say "Installing it asks for your macOS password and can download about 2 GB"
    say "of Apple developer tools. It usually takes 10-20 minutes."
    if ! prompt_yes_no "Install Homebrew now?" "yes"; then
        say_err "Homebrew is required for document conversion. The morning report is unaffected."
        exit 1
    fi
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
    # A fresh install is not on PATH yet in this shell.
    if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    command -v brew >/dev/null 2>&1 || { say_err "Homebrew was installed but is not on PATH. Close Terminal, open it again, and re-run this script."; exit 1; }
    say_ok "Homebrew installed."
}

step_libreoffice() {
    say_step "Installing LibreOffice and ffmpeg"
    if [[ -d /Applications/LibreOffice.app ]]; then
        say_ok "LibreOffice is already installed."
    else
        brew install --cask libreoffice
        say_ok "LibreOffice installed."
    fi
    if command -v ffmpeg >/dev/null 2>&1; then
        say_ok "ffmpeg is already installed."
    else
        brew install ffmpeg || say_warn "ffmpeg could not be installed — audio still works, joining is just less clean."
    fi
}

# convert.py calls the bare name `soffice`, resolved through PATH. The LibreOffice
# cask installs an app bundle and puts nothing on PATH, so without this symlink
# every conversion fails with "soffice not found".
step_soffice_symlink() {
    say_step "Making LibreOffice available to the skill"
    local prefix soffice_target
    prefix="$(brew --prefix)"
    soffice_target="/Applications/LibreOffice.app/Contents/MacOS/soffice"

    if [[ ! -x "$soffice_target" ]]; then
        say_err "LibreOffice is installed but $soffice_target is missing."
        exit 1
    fi
    mkdir -p "$prefix/bin"
    ln -sf "$soffice_target" "$prefix/bin/soffice"
    if command -v soffice >/dev/null 2>&1; then
        say_ok "soffice available at $(command -v soffice)"
    else
        say_warn "soffice is linked into $prefix/bin but that folder is not on PATH."
        say_dim  "  The gateway captures the shell PATH, so run: hermes gateway install --force"
    fi
}

# The Hermes venv is created with `uv venv` and no `--seed` (install.sh setup_venv),
# so that interpreter has **no pip at all** — `python3 -m pip install` fails there.
# uv is the tool that populated it and Hermes keeps its own copy at ~/.hermes/bin/uv.
# Order: pip if it happens to exist → uv → bootstrap pip with ensurepip.
install_packages_into() {
    local py="$1" uv

    if "$py" -m pip --version >/dev/null 2>&1; then
        say_dim "  Installing with pip"
        "$py" -m pip install --quiet "${PIP_PACKAGES[@]}" && return 0
    fi

    uv="$HOME/.hermes/bin/uv"
    [[ -x "$uv" ]] || uv="$(command -v uv 2>/dev/null || true)"
    if [[ -n "$uv" && -x "$uv" ]]; then
        say_dim "  Installing with uv (this environment has no pip)"
        "$uv" pip install --python "$py" --quiet "${PIP_PACKAGES[@]}" && return 0
    fi

    say_dim "  Adding pip to the environment first"
    "$py" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "$py" -m pip install --quiet "${PIP_PACKAGES[@]}"
}

step_python_packages() {
    say_step "Installing the Python packages the conversion needs"
    local py
    py="$(resolve_skill_python)"
    say_dim "  Using the interpreter the skill itself runs under: $py"

    if [[ "$py" != *"/venv/bin/python3" ]]; then
        say_warn "The Hermes environment was not found, so the packages go into the system Python."
        say_warn "If conversion later says a module is missing, re-run this script after the gateway is installed."
    fi

    if ! install_packages_into "$py"; then
        say_err "Could not install the Python packages into $py"
        exit 1
    fi
    say_ok "Packages installed: ${PIP_PACKAGES[*]}"
    printf '%s' "$py" >"$HOME/.hermes/.doc-convert-python"
}

step_copy_skill() {
    say_step "Installing the document conversion skill"
    mkdir -p "$HOME/.hermes/skills"
    # Copy, not symlink — see install-mac.sh. `state/` holds Google credentials and
    # output history, so it must survive a re-run: no --delete here.
    rsync -a "$SRC_DIR/skills/doc-convert/" "$D2_DEST/"
    [[ -f "$D2_DEST/SKILL.md" ]] || { say_err "Skill was not copied to $D2_DEST"; exit 1; }
    say_ok "Skill installed at $D2_DEST"
}

step_preflight() {
    say_step "Checking everything works"
    local py output
    py="$(cat "$HOME/.hermes/.doc-convert-python" 2>/dev/null || resolve_skill_python)"
    output="$("$py" "$D2_DEST/scripts/preflight.py" --compact 2>&1)" || true
    if printf '%s' "$output" | grep -q '"success": *true'; then
        say_ok "Document conversion is ready."
        return 0
    fi
    say_err "Document conversion is not ready yet:"
    printf '%s\n' "$output"
    exit 1
}

main() {
    say "${C_BOLD}Document conversion add-on (Word / PowerPoint / PDF)${C_RESET}"
    require_tty
    step_check_d1
    step_homebrew
    step_libreoffice
    step_soffice_symlink
    step_copy_skill
    step_python_packages
    step_preflight
    say ""
    say "Try it: send a .docx file to the bot in Telegram and ask for a PowerPoint."
    if [[ "$CHAINED" != "true" ]]; then
        say_dim "Google Docs/Slides access is a separate, optional step — see docs/install-mac.md."
    fi
}

main "$@"
