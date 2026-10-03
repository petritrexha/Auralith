"""Card visuals: keep agent-written Mermaid safe and small, and turn it into text for the terminal.

The web page and the VS Code extension render the Mermaid diagram itself; a terminal can't, so
`flow_lines` turns the same diagram into 1-4 readable lines like "Request → Logger → Auth → Handler".
"""
from __future__ import annotations

import re

DIAGRAM_TYPES = ("graph", "flowchart", "sequenceDiagram", "stateDiagram", "stateDiagram-v2", "classDiagram", "erDiagram")
MAX_LINES = 25
MAX_CHARS = 1500
# Interactivity, raw HTML and init directives have no place in a teaching diagram.
UNSAFE = re.compile(r"(?i)(^\s*click\s|%%\{|<script|javascript:|href\s*=|<iframe|<img)")


def clean_mermaid(text: str) -> str:
    """Return a safe, small Mermaid diagram, or "" when the input isn't one."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", text).strip()
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines or not lines[0].strip().split()[0].startswith(DIAGRAM_TYPES):
        return ""
    if any(UNSAFE.search(l) for l in lines):
        return ""
    lines = [l for l in lines if not re.match(r"\s*(style|classDef|class|linkStyle)\s", l)]  # app styles them
    return "\n".join(lines[:MAX_LINES])[:MAX_CHARS]


_NODE = r"([A-Za-z0-9_]+)\s*(\[\(.*?\)\]|\[\[.*?\]\]|\[.*?\]|\(\(.*?\)\)|\(.*?\)|\{.*?\})?"
_ARROW = r"\s*(-->|==>|-\.->|---|-\.-|--[^-|>]+-->|-\.[^.]+\.->|-\.[^.]+\.-)\s*(?:\|([^|]*)\|)?\s*"


def _label(shape: str | None) -> str:
    if not shape:
        return ""
    inner = re.sub(r"^[\[\(\{]+|[\]\)\}]+$", "", shape).strip().strip('"')
    return re.sub(r"<br\s*/?>", " ", inner)


def flow_lines(diagram: str, limit: int = 4) -> list[str]:
    """Plain-text version of a flowchart or sequence diagram (best effort, never raises)."""
    try:
        lines = [l.strip() for l in (diagram or "").splitlines() if l.strip()]
        if not lines:
            return []
        kind = lines[0].split()[0]
        if kind.startswith("sequenceDiagram"):
            return _sequence(lines[1:], limit)
        if kind in ("graph", "flowchart"):
            return _flowchart(lines[1:], limit)
    except Exception:
        pass
    return []


def _flowchart(lines: list[str], limit: int) -> list[str]:
    names: dict[str, str] = {}
    for line in lines:
        for node_id, shape in re.findall(_NODE, line):
            if shape:
                names[node_id] = _label(shape)
    out = []
    for line in lines:
        parts = re.split(_ARROW, line)
        if len(parts) < 4:  # no arrow on this line
            continue
        text = ""
        # parts = [node, arrow, label, node, arrow, label, node, ...]
        for i in range(0, len(parts), 3):
            m = re.match(_NODE, parts[i].strip())
            if not m:
                break
            name = names.get(m.group(1)) or _label(m.group(2)) or m.group(1)
            if i:
                edge = (parts[i - 1] or "").strip()
                arrow_text = re.sub(r"^[-.=]+|[-.=>]+$", "", parts[i - 2]).strip()
                tag = edge or arrow_text
                text += f" →({tag}) " if tag else " → "
            text += name
        if text:
            out.append(text)
    return _merge_chains(out)[:limit]


def _merge_chains(lines: list[str]) -> list[str]:
    """Join "A → B" and "B → C" into "A → B → C" so simple pipelines read as one line."""
    merged: list[str] = []
    for line in lines:
        if merged and " → " in line and "→(" not in line:
            head = line.split(" → ", 1)
            if merged[-1].endswith(head[0]) and "→(" not in merged[-1]:
                merged[-1] += " → " + head[1]
                continue
        merged.append(line)
    return merged


def _sequence(lines: list[str], limit: int) -> list[str]:
    names: dict[str, str] = {}
    out = []
    for line in lines:
        m = re.match(r"(?:participant|actor)\s+(\S+)(?:\s+as\s+(.+))?$", line)
        if m:
            names[m.group(1)] = (m.group(2) or m.group(1)).strip()
            continue
        m = re.match(r"(\S+?)\s*(-{1,2}>>|-{1,2}>|-{1,2}x|-{1,2}\))\s*(\S+?)\s*:\s*(.+)$", line)
        if m:
            a, b = names.get(m.group(1), m.group(1)), names.get(m.group(3), m.group(3))
            out.append(f"{a} → {b}: {m.group(4).strip()}" if a != b else f"{a}: {m.group(4).strip()}")
    return out[:limit]


def first_sentences(text: str, n: int) -> str:
    """Trim prose to its first n sentences (used for the 'brief' depth)."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z`(])", (text or "").strip())
    return " ".join(parts[:n]).strip()
