"""
guardrails.py — Week 2: PII minimization for intake.

The primary guardrail is structural, not this file: db.py's schema has
no passport_number column at all, and intake.py never asks for one —
only `nationality` (the visa-relevant fact Week 4's border/visa checks
will actually need). You can't leak a field you never collect.

This module is the defense-in-depth layer for the fields that *are*
free text (hard_constraints, date_flexibility) — someone might paste a
passport number into "hard constraints: my passport is X1234567,
expires 2027" without thinking about it. We scrub anything that looks
like one before it's ever written to disk, and say so.

Disclosed limitation: this is a regex heuristic, not a real passport
validator — it will miss unusual formats and can false-positive on
things like flight confirmation codes. It is a safety net, not a
guarantee. If real PII detection ever matters more than it does for a
hobby project, this is the first thing to replace with something
better, not trust blindly.
"""

import re

# Common passport-number shapes: 6-9 characters, at least one letter and
# one digit, no spaces — covers the US (9 digits), UK/most-EU (9
# alphanumeric), and many other formats closely enough to be useful as
# a net, not a validator.
_PASSPORT_LIKE = re.compile(
    r"\b(?=[A-Za-z0-9]{6,9}\b)(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{6,9}\b"
)

REDACTED_MARKER = "[redacted: looked like a passport/ID number]"


def scrub_passport_like(text: str) -> tuple[str, bool]:
    """Redact substrings that look like a passport/ID number.

    Returns (clean_text, was_redacted). Deliberately over-eager rather
    than under-eager: a false positive costs a person re-typing a
    flight code; a false negative writes an ID number to disk.
    """
    if not text:
        return text, False

    redacted = False

    def _replace(match: re.Match) -> str:
        nonlocal redacted
        redacted = True
        return REDACTED_MARKER

    clean = _PASSPORT_LIKE.sub(_replace, text)
    return clean, redacted
