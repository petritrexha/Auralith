"""SessionStart hook (runs async) and manual connection test.

As a hook: silently pings the server so the Setup page can show "Connected".
Manually:  python plugin/scripts/ping.py   → prints whether URL + token work.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnloop_common as ll  # noqa: E402


def main(interactive: bool) -> int:
    cfg = ll.config()
    if not cfg["url"] or not cfg["token"]:
        if interactive:
            print("LearnLoop is not configured. Set the server URL and token in the plugin settings,")
            print("or export LEARNLOOP_URL and LEARNLOOP_TOKEN.")
        return 1
    result = ll.api_call("GET", "/api/v1/ping", timeout=5)
    if interactive:
        if result and result.get("ok"):
            print(f"✅ Connected to {cfg['url']} as {result.get('user')}")
            return 0
        status = (result or {}).get("_status")
        print(f"❌ Could not connect to {cfg['url']}" + (f" (HTTP {status})" if status else " (server unreachable)"))
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252 and choke on the emoji
    except Exception:
        pass
    interactive = sys.stdin is None or sys.stdin.isatty()
    if not interactive:
        ll.read_hook_input()  # drain hook payload
    try:
        code = main(interactive)
    except Exception as exc:
        ll.debug(f"ping error: {exc!r}")
        code = 0
    sys.exit(code if interactive else 0)
