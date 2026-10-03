"""Stop hook: when the agent finishes a turn, send the batch to LearnLoop and show any cards.

Output is a JSON object with `systemMessage`, which Claude Code shows to the *user* at the end
of the turn. Nothing is added to the coding agent's context, so LearnLoop costs the agent nothing.
Silent no-op when unconfigured, offline or when nothing new came up. Always exit 0.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnloop_common as ll  # noqa: E402
from collect import change_from_tool  # noqa: E402

WIDTH = 88


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_card(card: dict) -> str:
    """Compact ~6-8 line block that reads fine in a plain terminal."""
    head = f"💡 LearnLoop · {card.get('concept', 'New concept')}"
    if card.get("category"):
        head += f"  [{card['category']}]"
    lines = [head]
    lines += textwrap.wrap(_clip(card.get("summary", ""), 260), WIDTH)
    if card.get("why_here"):
        lines += textwrap.wrap("Here: " + _clip(card["why_here"], 200), WIDTH)
    if card.get("url"):
        lines.append(f"Read more → {card['url']}")
    return "\n".join(lines)


def load_batch(session_id: str) -> list[dict]:
    path = ll.batch_path(session_id)
    if not path.exists():
        return []
    sending = path.with_suffix(".sending")
    try:
        os.replace(path, sending)  # atomic: edits made while we send go into a fresh batch
    except OSError:
        return []
    changes = []
    with open(sending, encoding="utf-8") as fh:
        for line in fh:
            try:
                changes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    try:
        sending.unlink()
    except OSError:
        pass
    return changes


def read_turn(transcript_path: str) -> tuple[list[tuple[str, dict]], str]:
    """Read this turn from Claude Code's session transcript (JSONL): its tool calls and the agent's last text.

    "This turn" = everything after the last real user prompt (not a tool result).
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return [], ""
    tool_calls: list[tuple[str, dict]] = []
    last_text = ""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or {}
                content = msg.get("content")
                if rec.get("type") == "user":
                    is_tool_result = isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
                    )
                    if not is_tool_result and not rec.get("isMeta"):
                        tool_calls, last_text = [], ""  # a new prompt starts a new turn
                elif rec.get("type") == "assistant" and isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls.append((block.get("name", ""), block.get("input") or {}))
                        elif isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                            last_text = block["text"]
    except OSError:
        pass
    return tool_calls, last_text


def changes_from_transcript(tool_calls: list[tuple[str, dict]], cwd: str) -> list[dict]:
    """Backup path when the PostToolUse hook collected nothing: rebuild the edits from the transcript."""
    changes = []
    for name, tool_input in tool_calls:
        entry = change_from_tool(name, tool_input, cwd)
        if entry:
            changes.append(entry)
    ll.debug(f"flush: transcript fallback found {len(changes)} edits in {len(tool_calls)} tool calls: {[n for n, _ in tool_calls][:15]}")
    return changes


def load_acks() -> list[int]:
    try:
        return [int(i) for i in json.loads(ll.ack_path().read_text(encoding="utf-8"))][-50:]
    except Exception:
        return []


def save_acks(ids: list[int]) -> None:
    try:
        ll.ack_path().write_text(json.dumps(ids[-50:]), encoding="utf-8")
    except OSError:
        pass


def once_a_day(kind: str) -> bool:
    """True the first time a notice kind is requested today."""
    marker = ll.notice_path(kind)
    if marker.exists():
        return False
    try:
        marker.touch()
    except OSError:
        pass
    return True


def notice_for(result: dict, cfg: dict) -> str:
    """One line explaining why no cards came back, when the user would otherwise be left guessing."""
    if result.get("_status") == 401:
        return "LearnLoop: your token was rejected. Get a new one on the Setup page."
    if result.get("_timeout"):
        return (f"LearnLoop is still writing cards for this turn. They will show after your next prompt, "
                f"and they are already on the web: {cfg['url']}/app/cards/")
    if result.get("_status") == 429 and once_a_day("ratelimit"):
        return "LearnLoop: hourly limit reached, so no cards for a bit. Your edits are not lost."
    if result.get("outcome") == "daily_limit" and once_a_day("daily"):
        return f"LearnLoop: you reached today's card limit. Raise it in Settings: {cfg['url']}/app/settings/"
    return ""


def main() -> None:
    data = ll.read_hook_input()
    cfg = ll.config()
    session_id = data.get("session_id", "default")
    ll.debug(f"flush: hook fired session={str(session_id)[:8]} url_set={bool(cfg['url'])} token_set={bool(cfg['token'])}")
    if cfg["disabled"]:
        return
    changes = load_batch(session_id)
    agent_message = data.get("last_assistant_message") or ""
    if not changes or not agent_message:  # the transcript can be large: only read it when something is missing
        tool_calls, last_text = read_turn(data.get("transcript_path", ""))
        agent_message = agent_message or last_text
        if not changes:
            ll.debug("flush: no edits collected by the PostToolUse hook, checking the transcript")
            changes = changes_from_transcript(tool_calls, data.get("cwd", ""))
    if not changes:
        ll.debug("flush: no file edits this turn")
        return
    if not cfg["url"] or not cfg["token"]:
        ll.debug("flush: not configured (server URL / token missing)")
        return
    acks = load_acks()
    result = ll.api_call("POST", "/api/v1/analyze", {
        "session_id": session_id,
        "changes": changes,
        # The coding agent's own summary of the turn — lets LearnLoop explain *why*, not just *what*.
        "agent_message": ll.scrub(agent_message[:4000]),
        "ack": acks,
        "client": {"plugin_version": ll.VERSION},
    })
    ll.debug(f"flush: sent {len(changes)} changes → {str(result)[:300]}")
    if not result:
        return
    if "_status" not in result and not result.get("_timeout"):
        acks = []  # the server has recorded them
    cards = result.get("cards") or []
    save_acks(acks + [c["id"] for c in cards if isinstance(c.get("id"), int)])
    if cards:
        print(json.dumps({"systemMessage": "\n\n".join(format_card(c) for c in cards)}))
    elif notice := notice_for(result, cfg):
        print(json.dumps({"systemMessage": notice}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        ll.debug(f"flush error: {exc!r}")
    sys.exit(0)
