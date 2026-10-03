"""PostToolUse hook (Edit | Write | MultiEdit | NotebookEdit).

Turns the tool call into a small diff and appends it to this session's batch file.
No network, no output, always exit 0 — it must be instant and invisible.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnloop_common as ll  # noqa: E402


def _lines(prefix: str, text: str) -> list[str]:
    return [prefix + line for line in (text or "").splitlines()]


def build_diff(tool_name: str, tool_input: dict) -> str:
    """Accept the field names Claude Code uses today, plus a few aliases for safety."""
    ti = tool_input or {}
    if tool_name == "MultiEdit" or isinstance(ti.get("edits"), list):
        out = []
        for edit in ti.get("edits") or []:
            out += _lines("-", edit.get("old_string", "")) + _lines("+", edit.get("new_string", ""))
        return "\n".join(out)
    if "new_string" in ti or "old_string" in ti:  # Edit
        return "\n".join(_lines("-", ti.get("old_string", "")) + _lines("+", ti.get("new_string", "")))
    if tool_name == "NotebookEdit":
        return "\n".join(_lines("+", ti.get("new_source", "")))
    content = ti.get("content") or ti.get("file_text") or ""  # Write
    return "\n".join(_lines("+", content))


def display_path(path: str, cwd: str) -> str:
    try:
        rel = os.path.relpath(path, cwd) if cwd and os.path.isabs(path) else path
        if rel.startswith(".."):
            rel = path
        return rel.replace("\\", "/")
    except ValueError:  # different drives on Windows
        return path.replace("\\", "/")


def main() -> None:
    data = ll.read_hook_input()
    if ll.config()["disabled"]:
        return
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path") or ""
    if not path or ll.is_secret_file(path):
        ll.debug(f"collect: skipped {path!r}")
        return
    diff = build_diff(data.get("tool_name", ""), tool_input)
    if not diff.strip():
        return
    diff = ll.scrub(diff)[: ll.MAX_DIFF_CHARS]
    target = ll.batch_path(data.get("session_id", "default"))
    if target.exists() and target.stat().st_size > ll.MAX_BATCH_BYTES:
        ll.debug("collect: batch full, dropping change")
        return
    entry = {"file": display_path(path, data.get("cwd", "")), "diff": diff}
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    ll.debug(f"collect: +{entry['file']} ({len(diff)} chars)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the session
        ll.debug(f"collect error: {exc!r}")
    sys.exit(0)
