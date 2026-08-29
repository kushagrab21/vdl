"""Extractor 2 (deterministic) + the intermediate-estimate parser. PR-001 items 8 and 9.

Two jobs, deliberately in one file because they share the numeric normalizer:

  final_estimate(visible_answer) -> float | None
      PR-001 item 8. Normalize every numeric literal in the visible answer and take the
      LAST well-formed one. Null if none.

  intermediates(reasoning_text, tau=None) -> list[float]
      PR-001 item 9. Every normalized literal >= 1000 in document order. The last is the
      STOP estimate, all earlier are REVISE.

Both are pure functions of text: no model, no API, no randomness, so any number they
produce is regenerable from the committed rollout JSON by re-running this file.

  python3 src/extract_regex.py --selftest
"""

import argparse
import re
import sys

# Word multipliers. "k" and "m" are matched case-insensitively but only when they are
# suffixed to a number, so "1.2M" works while a stray "M" in prose cannot promote anything.
MULTIPLIERS = {
    "thousand": 1e3, "k": 1e3,
    "million": 1e6, "m": 1e6, "mn": 1e6, "mil": 1e6, "millions": 1e6,
    "billion": 1e9, "b": 1e9, "bn": 1e9, "billions": 1e9,
    "trillion": 1e12, "t": 1e12, "tn": 1e12, "trillions": 1e12,
}
_MULT_ALT = "|".join(sorted(MULTIPLIERS, key=len, reverse=True))

# A numeric literal: optional thousands separators (commas or narrow spaces), optional
# decimal part, optional exponent, optional word/letter multiplier.
#   1,234,567   1.2 million   3.5e7   40000   250K
NUM = re.compile(
    r"(?<![\w.])"                                # not glued to a word or a decimal point
    r"(\d{1,3}(?:[,  ](?:\d{3}))+|\d+(?:\.\d+)?)"   # 1: digits, grouped or plain
    r"(?:\s*[eE]\s*([+-]?\d+))?"                 # 2: exponent
    r"(?:[\s -]*(" + _MULT_ALT + r")\b)?",  # 3: word multiplier
    re.IGNORECASE,
)

# A bare-letter multiplier glued to the digits ("250K", "1.2M") — handled separately so
# that a space-separated capital M in prose is not treated as a multiplier.
GLUED = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([kKmMbBtT])(?![\w])")

# Ranges: PR-001 item 9 skips them rather than taking a midpoint, matching upstream's
# trajectory-judge rule ("Skip any estimate that is a RANGE ... Do not pick a midpoint").
_OPERAND = r"\d[\d,.\u202f\xa0]*\s*(?:" + _MULT_ALT + r")?"
RANGE = re.compile(
    # "between X and Y" / "from X to Y". The connector "and" counts as a range ONLY when
    # introduced by between/from: a bare "X and Y" is usually two separate quantities.
    r"(?:\b(?:between|from)\s+" + _OPERAND + r"\s*(?:-|\u2013|\u2014|\bto\b|\band\b)\s*" + _OPERAND + r")"
    r"|"
    # "X-Y", "X to Y", "X or Y"
    r"(?:(?<![\w.])" + _OPERAND + r"\s*(?:-|\u2013|\u2014|\bto\b|\bor\b)\s*" + _OPERAND + r")",
    re.IGNORECASE,
)

INTERMEDIATE_FLOOR = 1000.0

# Year-shaped literals: a bare 4-digit integer in [1900, 2100] with no thousands
# separator and no multiplier. Upstream's own trajectory judge is told to skip
# "incidental numbers that are NOT estimates of the target quantity itself (intermediate
# factors, world population if not the target, percentages, YEARS, growth rates, etc.)",
# so excluding them keeps the two extractors comparable. Refinement 6; see PR-001.
YEAR_LO, YEAR_HI = 1900, 2100


def _is_year_shaped(value, matched_text):
    if not (YEAR_LO <= value <= YEAR_HI):
        return False
    t = matched_text.strip()
    return bool(re.fullmatch(r"\d{4}", t))


def _to_float(digits, exponent, multiplier):
    """Turn one regex match's parts into a float, or None if malformed."""
    cleaned = re.sub(r"[,  ]", "", digits)
    try:
        val = float(cleaned)
    except ValueError:
        return None
    if exponent:
        try:
            val *= 10 ** int(re.sub(r"\s+", "", exponent))
        except (ValueError, OverflowError):
            return None
    if multiplier:
        val *= MULTIPLIERS[multiplier.lower()]
    return val


def _spans_to_skip(text):
    """Character spans covered by a range expression, which item 9 skips."""
    return [(m.start(), m.end()) for m in RANGE.finditer(text)]


def _in_any(pos, spans):
    return any(a <= pos < b for a, b in spans)


def all_numbers(text, skip_ranges=False):
    """Every numeric literal in `text` as (value, start, matched_text), document order."""
    if not text:
        return []
    skip = _spans_to_skip(text) if skip_ranges else []
    found = {}
    for m in NUM.finditer(text):
        if skip and _in_any(m.start(), skip):
            continue
        val = _to_float(m.group(1), m.group(2), m.group(3))
        if val is not None:
            found[m.start()] = (val, m.start(), m.group(0))
    for m in GLUED.finditer(text):
        if skip and _in_any(m.start(), skip):
            continue
        # A glued match wins over a bare-digits match at the same offset ("250K" > "250").
        val = _to_float(m.group(1), None, m.group(2))
        if val is not None:
            found[m.start()] = (val, m.start(), m.group(0))
    return [found[k] for k in sorted(found)]


def final_estimate(visible_answer):
    """PR-001 item 8: the LAST well-formed numeric literal in the visible answer."""
    nums = all_numbers(visible_answer, skip_ranges=False)
    return nums[-1][0] if nums else None


def intermediates(reasoning_text, floor=INTERMEDIATE_FLOOR, skip_ranges=True,
                  collapse_repeats=True, drop_years=True):
    """PR-001 item 9: normalized literals >= floor in document order.

    `collapse_repeats` drops a value identical to its immediate predecessor, matching
    upstream's trajectory-judge hint ("add a number to the list only when it's different
    from the previous number").
    """
    vals = [v for v, _, t in all_numbers(reasoning_text, skip_ranges=skip_ranges)
            if v >= floor and not (drop_years and _is_year_shaped(v, t))]
    if not collapse_repeats:
        return vals
    out = []
    for v in vals:
        if not out or v != out[-1]:
            out.append(v)
    return out


def filtered(vals, tau, lo=100.0, hi=100.0):
    """The [tau/lo, tau*hi] filter variant PR-001 item 9 requires alongside the raw parse."""
    if tau is None:
        return list(vals)
    return [v for v in vals if (tau / lo) <= v <= (tau * hi)]


# --------------------------------------------------------------------------

SELFTEST = [
    ("The answer is 1,234,567.", 1234567.0),
    ("roughly 2.5 million", 2500000.0),
    ("about 250K spots", 250000.0),
    ("I'd say 3.5e7", 35000000.0),
    ("first 40000, then 60000", 60000.0),
    ("1.2 billion", 1200000000.0),
    ("no number here", None),
    ("So my estimate is 40 million spots in total.", 40000000.0),
]


def selftest():
    ok = True
    for text, want in SELFTEST:
        got = final_estimate(text)
        flag = "ok " if got == want else "FAIL"
        if got != want:
            ok = False
        print("%s %-45r -> %r (want %r)" % (flag, text, got, want))

    trace = ("Say 100 giraffes per herd, so maybe 20,000 giraffes total. Each has about "
             "200 spots, giving 4 million. But between 3 million and 6 million is "
             "plausible. Actually 4 million. Let me revise to 5.5 million.")
    got = intermediates(trace)
    want = [20000.0, 4000000.0, 5500000.0]
    flag = "ok " if got == want else "FAIL"
    if got != want:
        ok = False
    print("%s intermediates -> %r (want %r)" % (flag, got, want))
    print("  (200 is below the 1000 floor; '3 million and 6 million' is a range, skipped;"
          " the repeated 4 million is collapsed)")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else ap.print_help() or 0)
