"""Keep notes.json in step with the notes in book.md.

Only what changed between book.raw.md (the pipeline's output) and book.md is
applied, so notes you didn't touch stay exactly as the pipeline wrote them:

  - a `[^id]: ...` line you edited  -> that note's `text`
  - a `[^id]: ...` line you deleted -> the note is dropped
  - a `[^id]: ...` line you added   -> a new note, status `manual`
  - a `[^id]` call you added        -> status `manual`
  - a `[^id]` call you deleted      -> status `unresolved`, `call` null
"""

from __future__ import annotations

import re
from pathlib import Path

from ..common import read_json, write_json
from .mdbook import NOTE_DEF

_call = re.compile(r"\[\^([^\]\s]+)\](?!:)")
_tail = re.compile(r"\s*<!--.*?-->\s*$", re.S)


def _parse(blocks: list[str]) -> tuple[dict[str, str], set[str]]:
    defs: dict[str, str] = {}
    calls: set[str] = set()
    for b in blocks:
        m = NOTE_DEF.match(b)
        if m:
            text = _tail.sub("", m.group(2)).rstrip()
            text = text[:-1].rstrip() if text.endswith("⚠") else text
            defs[m.group(1)] = text.replace("&lt;", "<")
        else:
            calls.update(_call.findall(b))
    return defs, calls


def sync(path: Path, raw: list[str], current: list[str]) -> None:
    if not path.exists():
        return
    data = read_json(path)
    raw_defs, raw_calls = _parse(raw)
    defs, calls = _parse(current)
    by_id = {n["id"]: n for n in data["notes"]}

    notes = []
    for n in data["notes"]:
        nid = n["id"]
        if nid in raw_defs and nid not in defs:
            continue
        if nid in defs and defs[nid] != raw_defs.get(nid):
            n["text"] = defs[nid]
        if nid in calls and nid not in raw_calls:
            n["status"] = "manual"
        elif nid in raw_calls and nid not in calls:
            n["status"], n["call"] = "unresolved", None
        notes.append(n)
    scope = None
    for nid in defs:                                    # in book order
        if nid in by_id:
            scope = by_id[nid].get("scope")
        elif nid not in raw_defs:
            notes.append(dict(id=nid, scope=scope, text=defs[nid], call=None,
                              status="manual" if nid in calls else "unresolved"))

    counts: dict = {}
    for n in notes:
        counts.setdefault(n.get("scope"), {}).setdefault(n["status"], 0)
        counts[n.get("scope")][n["status"]] += 1
    data["counts"], data["notes"] = counts, notes
    write_json(path, data)
