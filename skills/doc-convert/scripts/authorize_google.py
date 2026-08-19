#!/usr/bin/env python3
"""One-time Google OAuth authorization for doc-convert.

Reads state/google-creds/client_secret.json, runs the OAuth consent flow, and writes
state/google-creds/token.json (with a refresh token) so the skill can access Google
Workspace non-interactively afterwards.

Usage:
  python3 authorize_google.py            # opens a local-server flow on 127.0.0.1:<port>
  python3 authorize_google.py --port 8765

On a headless VPS (no browser): SSH-tunnel the port, e.g.
  ssh -L 8765:localhost:8765 <user>@<vps>
then run with --port 8765 and open the printed URL in your local browser.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from google_io import DEFAULT_CREDS_DIR, SCOPES, scope_set_name  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Authorize Google Workspace for doc-convert")
    ap.add_argument("--creds-dir", default=DEFAULT_CREDS_DIR)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret = os.path.join(args.creds_dir, "client_secret.json")
    if not os.path.exists(client_secret):
        print(f"THIẾU {client_secret}. Đặt file OAuth client (Desktop) vào đây trước.", file=sys.stderr)
        return 1

    print(f"Bộ quyền: {scope_set_name()}  ({len(SCOPES)} scope)", file=sys.stderr)
    for scope in SCOPES:
        print(f"  - {scope}", file=sys.stderr)
    if scope_set_name() == "minimal":
        print("  → chỉ thao tác với file do bot tạo; KHÔNG đọc được link Google riêng tư.",
              file=sys.stderr)
    print("Đổi bằng DOC_CONVERT_GOOGLE_SCOPES=minimal|private-links\n", file=sys.stderr)

    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
    # open_browser=False: in ra URL để mở thủ công (hợp cả WSL lẫn VPS qua SSH tunnel).
    creds = flow.run_local_server(
        host="127.0.0.1", port=args.port, open_browser=False,
        authorization_prompt_message="Mở URL này trong trình duyệt để đăng nhập Google:\n{url}",
        success_message="Xong! Có thể đóng tab này và quay lại terminal.",
    )

    token_path = os.path.join(args.creds_dir, "token.json")
    with open(token_path, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())
    os.chmod(token_path, 0o600)
    print(f"OK: đã lưu token vào {token_path}. Google Workspace sẵn sàng cho doc-convert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
