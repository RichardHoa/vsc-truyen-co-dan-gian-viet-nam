"""Vietnamese orthography checks, used to tag each page as Vietnamese, other
language, or mixed.

Every Vietnamese word is one syllable of the shape
    initial? + vowel nucleus + final?
with a fixed inventory. Romanised Cham / Raglai / Ba Na / Mơ Nông words very
often break that shape (Klu, Hbia, mnĭh, plây, ngõq, bblwak), so the share of
invalid syllables among lowercase words separates the languages well.
"""

from __future__ import annotations

import re
import unicodedata

TONE_MARKS = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323"}  # huyền sắc ngã hỏi nặng

_SYLLABLE = re.compile(
    r"^(ngh|ng|gh|gi|kh|nh|ph|qu|th|tr|ch|[bcdđghklmnprstvx])?"
    r"[aăâeêioôơuưy]{1,3}"
    r"(ch|nh|ng|[cmnpt])?$"
)
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)


def strip_tones(word: str) -> str:
    d = unicodedata.normalize("NFD", word)
    return unicodedata.normalize("NFC", "".join(c for c in d if c not in TONE_MARKS))


def is_vietnamese_syllable(word: str) -> bool:
    w = strip_tones(word.casefold())
    if w == "gi" or w == "gin":  # gi + (i) edge cases
        return True
    return bool(_SYLLABLE.match(w))


def invalid_ratio(text: str) -> tuple[float, int]:
    """Share of words that are not Vietnamese syllables. Capitalised words are
    left out (when there are enough others): they are mostly proper names, which
    a Vietnamese translation repeats often ("Chiêng Poh Way Takai Gok nói:"),
    while real original-language text is mostly lowercase words."""
    words = _TOKEN.findall(text)
    lower = [w for w in words if not w[0].isupper()]
    if len(lower) >= 8:
        words = lower
    if not words:
        return 0.0, 0
    bad = sum(1 for w in words if not is_vietnamese_syllable(w))
    return bad / len(words), len(words)


def guess_language(text: str) -> dict:
    ratio, n = invalid_ratio(text)
    if n < 8:
        guess = "unknown"
    elif ratio < 0.12:
        guess = "vi"
    elif ratio < 0.35:
        guess = "mixed"
    else:
        guess = "other"
    return dict(guess=guess, invalid_ratio=round(ratio, 3), words=n)
