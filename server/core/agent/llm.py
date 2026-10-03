"""Thin wrapper around the Anthropic SDK that tracks usage and supports a tool-use loop."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from django.conf import settings

log = logging.getLogger("core.agent")


def ai_mode() -> str:
    """'live' when a key is configured and mock isn't forced, else 'mock'."""
    cfg = settings.LEARNLOOP
    if cfg["MOCK_AI"] or not cfg["ANTHROPIC_API_KEY"]:
        return "mock"
    return "live"


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class AgentRun:
    """Result of a tool-use loop."""

    usage: Usage = field(default_factory=Usage)
    trace: list[dict] = field(default_factory=list)
    stopped_by: str = "end_turn"  # end_turn | max_turns | budget | error
    final_text: str = ""


def _client():
    import anthropic  # imported lazily so mock mode works without the package configured

    return anthropic.Anthropic(api_key=settings.LEARNLOOP["ANTHROPIC_API_KEY"], timeout=20.0, max_retries=0)


def run_tool_loop(
    *,
    system: str,
    user_message: str,
    tools: list[dict],
    handlers: dict[str, Callable[[dict], Any]],
    max_turns: int,
    deadline: float,
    max_tokens: int = 1500,
    should_stop: Callable[[], bool] | None = None,
) -> AgentRun:
    """Classic agent loop: call the model, run any tools it asks for, feed results back, repeat.

    Stops when the model ends its turn, when `should_stop()` says the job is done,
    when the turn limit is hit, or when the wall-clock deadline would be exceeded.
    """
    import json

    run = AgentRun()
    client = _client()
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for turn in range(max_turns):
        # Each Haiku call is usually 1-4s; don't start one we can't finish.
        if time.monotonic() > deadline - 2.5:
            run.stopped_by = "budget"
            run.trace.append({"type": "stop", "reason": "time budget reached"})
            break
        try:
            resp = client.messages.create(
                model=settings.LEARNLOOP["MODEL"],
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
                # Never let one slow call blow the budget: the plugin is waiting on this response.
                timeout=max(deadline - time.monotonic(), 2.0),
            )
        except Exception as exc:  # network, auth, overload… never crash the request
            log.warning("LLM call failed: %s", exc)
            run.stopped_by = "error"
            run.trace.append({"type": "error", "message": str(exc)[:300]})
            break

        run.usage.calls += 1
        run.usage.input_tokens += getattr(resp.usage, "input_tokens", 0) or 0
        run.usage.output_tokens += getattr(resp.usage, "output_tokens", 0) or 0

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                run.final_text = block.text.strip()
                run.trace.append({"type": "thought", "turn": turn, "text": block.text.strip()[:600]})
            elif block.type == "tool_use":
                handler = handlers.get(block.name)
                try:
                    result = handler(block.input) if handler else {"error": f"unknown tool {block.name}"}
                except Exception as exc:  # a bad tool input shouldn't kill the loop
                    log.exception("tool %s failed", block.name)
                    result = {"error": str(exc)[:300]}
                run.trace.append({"type": "tool", "turn": turn, "tool": block.name, "input": _short(block.input), "result": _short(result)})
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)})

        if resp.stop_reason != "tool_use" or not tool_results:
            run.stopped_by = "end_turn"
            break
        messages.append({"role": "user", "content": tool_results})
        if should_stop and should_stop():
            run.stopped_by = "done"
            run.trace.append({"type": "stop", "reason": "agent finished its work"})
            break
    else:
        run.stopped_by = "max_turns"
        run.trace.append({"type": "stop", "reason": "turn limit reached"})
    return run


def _short(value: Any, limit: int = 400) -> Any:
    """Keep traces small enough to store and show."""
    import json

    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return value
    return text[:limit] + "…"
