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


def main() -> None:
    data = ll.read_hook_input()
    cfg = ll.config()
    session_id = data.get("session_id", "default")
    if cfg["disabled"]:
        return
    changes = load_batch(session_id)
    if not changes:
        return
    if not cfg["url"] or not cfg["token"]:
        ll.debug("flush: not configured (server URL / token missing)")
        return
    result = ll.api_call("POST", "/api/v1/analyze", {
        "session_id": session_id,
        "changes": changes,
        # The coding agent's own summary of the turn — lets LearnLoop explain *why*, not just *what*.
        "agent_message": ll.scrub((data.get("last_assistant_message") or "")[:4000]),
        "client": {"plugin_version": ll.VERSION},
    })
    ll.debug(f"flush: sent {len(changes)} changes → {str(result)[:300]}")
    if not result:
        return
    cards = result.get("cards") or []
    if result.get("_status") == 401:
        print(json.dumps({"systemMessage": "LearnLoop: your token was rejected. Get a new one on the Setup page."}))
        return
    if not cards:
        return
    message = "\n\n".join(format_card(c) for c in cards)
    print(json.dumps({"systemMessage": message}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        ll.debug(f"flush error: {exc!r}")
    sys.exit(0)
