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


EDIT_FIELDS = ("old_string", "new_string", "content", "file_text", "edits", "new_source")


def change_from_tool(tool_name: str, tool_input: dict, cwd: str) -> dict | None:
    """Return {"file", "diff"} for a file-editing tool call, or None for anything else (Read, Bash, …)."""
    if not isinstance(tool_input, dict) or not any(k in tool_input for k in EDIT_FIELDS):
        return None
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path") or ""
    if not path:
        return None
    if ll.is_secret_file(path):
        ll.debug(f"collect: skipped secret file {path!r}")
        return None
    diff = build_diff(tool_name, tool_input)
    if not diff.strip():
        return None
    return {"file": display_path(path, cwd), "diff": ll.scrub(diff)[: ll.MAX_DIFF_CHARS]}


def main() -> None:
    data = ll.read_hook_input()
    tool_name = data.get("tool_name", "")
    ll.debug(f"collect: hook fired tool={tool_name!r} session={str(data.get('session_id'))[:8]}")
    if ll.config()["disabled"]:
        return
    entry = change_from_tool(tool_name, data.get("tool_input") or {}, data.get("cwd", ""))
    if entry is None:
        return
    diff = entry["diff"]
    target = ll.batch_path(data.get("session_id", "default"))
    if target.exists() and target.stat().st_size > ll.MAX_BATCH_BYTES:
        ll.debug("collect: batch full, dropping change")
        return
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    ll.debug(f"collect: +{entry['file']} ({len(diff)} chars)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the session
        ll.debug(f"collect error: {exc!r}")
    sys.exit(0)
