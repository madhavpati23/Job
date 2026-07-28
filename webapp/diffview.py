"""Render a before/after diff of the tailored resume.

A rewrite you can't inspect is a rewrite you have to re-read in full. This marks
what the model added, cut, and left alone so the user can check any new claim
against their real experience — the one review step that shouldn't be skipped.

Diffing is line-level first (resume lines are semantic units: a bullet, a role,
a heading), then word-level inside changed blocks so a reworded bullet doesn't
render as a wholesale delete plus insert.
"""

from __future__ import annotations

import difflib
import html
import re

_WORD_SPLIT = re.compile(r"(\s+)")

# Chosen to stay legible on Streamlit's light and dark themes: translucent
# backgrounds tint whatever is behind them rather than fighting it.
_ADD_BG = "rgba(46, 160, 67, 0.28)"
_DEL_BG = "rgba(248, 81, 73, 0.22)"


def _words(line: str) -> list[str]:
    return [w for w in _WORD_SPLIT.split(line) if w]


def _mark(text: str, kind: str) -> str:
    safe = html.escape(text)
    if kind == "add":
        return f'<span style="background-color:{_ADD_BG};border-radius:3px;">{safe}</span>'
    if kind == "del":
        return (
            f'<span style="background-color:{_DEL_BG};border-radius:3px;'
            f'text-decoration:line-through;opacity:0.75;">{safe}</span>'
        )
    return safe


def _inline(old: str, new: str) -> tuple[str, str]:
    """Word-level diff of two similar lines."""
    a, b = _words(old), _words(new)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    left, right = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            left.append(_mark("".join(a[i1:i2]), "same"))
            right.append(_mark("".join(b[j1:j2]), "same"))
        else:
            if i1 != i2:
                left.append(_mark("".join(a[i1:i2]), "del"))
            if j1 != j2:
                right.append(_mark("".join(b[j1:j2]), "add"))
    return "".join(left), "".join(right)


def summarize(original: str, tailored: str) -> dict[str, int]:
    """Counts of added / removed / reworded lines."""
    a = original.splitlines()
    b = tailored.splitlines()
    stats = {"added": 0, "removed": 0, "reworded": 0, "unchanged": 0}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            stats["unchanged"] += i2 - i1
        elif tag == "insert":
            stats["added"] += j2 - j1
        elif tag == "delete":
            stats["removed"] += i2 - i1
        else:
            stats["reworded"] += max(i2 - i1, j2 - j1)
    return stats


def render_html(original: str, tailored: str) -> str:
    """Single-column diff: new content highlighted, cut content struck through."""
    a = original.splitlines()
    b = tailored.splitlines()
    out: list[str] = []

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for line in b[j1:j2]:
                out.append(_mark(line, "same") or "&nbsp;")
        elif tag == "insert":
            for line in b[j1:j2]:
                out.append(_mark(line, "add") if line.strip() else "&nbsp;")
        elif tag == "delete":
            for line in a[i1:i2]:
                if line.strip():
                    out.append(_mark(line, "del"))
        else:
            old_block, new_block = a[i1:i2], b[j1:j2]
            for idx in range(max(len(old_block), len(new_block))):
                old_line = old_block[idx] if idx < len(old_block) else ""
                new_line = new_block[idx] if idx < len(new_block) else ""
                if old_line and new_line:
                    # Only diff inline when the lines are actually related;
                    # otherwise word-level noise is worse than a clean swap.
                    ratio = difflib.SequenceMatcher(None, old_line, new_line).ratio()
                    if ratio > 0.4:
                        _, right = _inline(old_line, new_line)
                        out.append(right)
                    else:
                        out.append(_mark(old_line, "del"))
                        out.append(_mark(new_line, "add"))
                elif new_line:
                    out.append(_mark(new_line, "add"))
                elif old_line.strip():
                    out.append(_mark(old_line, "del"))

    body = "<br>".join(out)
    return (
        '<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        'font-size:0.85rem;line-height:1.7;white-space:pre-wrap;'
        'word-break:break-word;padding:1rem;border-radius:0.5rem;'
        'border:1px solid rgba(128,128,128,0.3);">'
        f"{body}</div>"
    )
