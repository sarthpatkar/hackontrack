"""Hindi vs Marathi detection. Both use Devanagari, and LLMs often confuse them, so use marker words."""
from __future__ import annotations

import re

_HI = set("है हैं और का की के को नहीं में से गया किया रहा रही था थी लिए देगी देंगे करें परिवार कृपया".split())
_MR = set("आहे आहेत आणि नाही मध्ये साठी होते होता देणार तुम्ही करा कुटुंब कुटुंबाला आपल्या त्यांनी पाठवा".split())


def detect_indic(text: str) -> str | None:
    """Return "hi" or "mr" when the text is mostly Devanagari and the markers are decisive, else None."""
    letters = [c for c in text if c.isalpha()]
    if not letters or sum("\u0900" <= c <= "\u097f" for c in letters) / len(letters) < 0.3:
        return None
    words = re.findall(r"[\u0900-\u097f]+", text)
    hi = sum(w in _HI for w in words)
    mr = sum(w in _MR for w in words)
    if mr > hi:
        return "mr"
    if hi > mr:
        return "hi"
    return None
