import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def chart_bars(rows):
    """Present existing daily counts on a common scale without client dependencies."""
    rows = list(rows or [])
    maximum = max((row["count"] for row in rows), default=0) or 1
    return [{**row, "height": round(row["count"] / maximum * 100)} for row in rows]


def _inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"_\(([^)]+)\)_", r"<em>(\1)</em>", text)
    return text


@register.filter
def markdown_lite(value: str) -> str:
    """Tiny, safe markdown: headings, bullet lists, bold/italic, inline code, paragraphs. Input is escaped first."""
    out, in_list = [], False
    for raw in escape(value or "").splitlines():
        line = raw.rstrip()
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if line.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if m:
            level = min(len(m.group(1)) + 1, 5)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return mark_safe("\n".join(out))


@register.filter
def pct(value) -> str:
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "–"
