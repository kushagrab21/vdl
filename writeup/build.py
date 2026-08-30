"""Build writeup/final.md from final.md.tmpl by substituting every numeric value from a file.

    python3 writeup/build.py            # build + run the no-hand-typed-digits check
    python3 writeup/build.py --verify   # rebuild and assert the on-disk file is identical
    python3 writeup/build.py --manifest # print the resolved manifest (token -> file -> value)

The contract this file enforces:

  1. `final.md.tmpl` contains prose and `{{token}}` placeholders. It contains no result number.
  2. `manifest.csv` has ONE LINE PER PLACEHOLDER: token, source file (in analysis/out/),
     selector (a CSV row filter + column, or a JSON path), format, note.
  3. Every value is read from a committed generated file. Nothing is typed.
  4. After substitution, EVERY DIGIT in the built file must be either (a) inside a span written
     by a placeholder, or (b) matched by a named structural whitelist rule -- dates, ledger
     entry ids, packet ids, section and item references, model and hardware names. Anything
     else is a VIOLATION and the build exits non-zero.

Stdlib only, so `python3 writeup/build.py` works on a clean checkout with no environment.
"""

import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "analysis", "out")
MANIFEST = os.path.join(HERE, "manifest.csv")
CHECK_OUT = os.path.join(OUT, "w10_digits_check.txt")

# (template, output). The markdown document is the deliverable; the compact page is the
# same evidence laid out visually, built from the SAME manifest so the two cannot drift.
TARGETS = [("final.md.tmpl", "final.md"), ("compact.html.tmpl", "compact.html")]

TOKEN_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

_CACHE = {}


# ------------------------------------------------------------------ sources

def load(source):
    if source in _CACHE:
        return _CACHE[source]
    path = os.path.join(OUT, source)
    if source.endswith(".csv"):
        with open(path) as fh:
            val = list(csv.DictReader(fh))
    else:
        with open(path) as fh:
            val = json.load(fh)
    _CACHE[source] = val
    return val


def csv_lookup(table, selector, source):
    """selector = 'col=val;col=val::field'  (filters may be empty)."""
    if "::" not in selector:
        raise ValueError("%s: CSV selector needs '::field' (got %r)" % (source, selector))
    filt, field = selector.rsplit("::", 1)
    rows = table
    if filt.strip():
        for clause in filt.split(";"):
            col, _, val = clause.partition("=")
            rows = [r for r in rows if r[col.strip()] == val]
    if len(rows) != 1:
        raise ValueError("%s [%s] matched %d rows, need exactly 1" % (source, filt, len(rows)))
    if field not in rows[0]:
        raise ValueError("%s: no column %r" % (source, field))
    return rows[0][field]


def json_lookup(doc, selector, source):
    """selector = 'a.b[2].c'."""
    cur = doc
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", selector):
        if part.startswith("["):
            cur = cur[int(part[1:-1])]
        else:
            if part not in cur:
                raise ValueError("%s: no key %r in path %r" % (source, part, selector))
            cur = cur[part]
    return cur


# ------------------------------------------------------------------ formatting

MINUS = "\u2212"                    # typographic minus, so tables line up


def fmt(value, spec):
    """Numeric specs render a negative sign as U+2212; `raw` is passed through untouched
    (model ids and commit hashes contain hyphens that must not be rewritten)."""
    if spec in ("", "raw"):
        return str(value)
    if spec == "int":
        return ("%d" % round(float(value))).replace("-", MINUS)
    if spec == "comma":
        return "{:,}".format(int(round(float(value)))).replace("-", MINUS)
    m = re.fullmatch(r"f(\d)", spec)
    if m:
        return (("%." + m.group(1) + "f") % float(value)).replace("-", MINUS)
    m = re.fullmatch(r"s(\d)", spec)
    if m:
        return (("%+." + m.group(1) + "f") % float(value)).replace("-", MINUS)
    m = re.fullmatch(r"x100_(\d)", spec)
    if m:
        return (("%." + m.group(1) + "f") % (100.0 * float(value))).replace("-", MINUS)
    m = re.fullmatch(r"pct(\d)", spec)
    if m:
        return (("%." + m.group(1) + "f") % float(value)).replace("-", MINUS)
    if spec == "p3":
        v = float(value)
        return "<0.001" if v < 0.001 else "%.3f" % v
    if spec == "sci":
        return "%.3g" % float(value)
    raise ValueError("unknown format spec %r" % spec)


# ------------------------------------------------------------------ manifest

def read_manifest():
    with open(MANIFEST) as fh:
        rows = [r for r in csv.DictReader(fh)
                if r.get("token") and not r["token"].startswith("#")]
    seen = {}
    for r in rows:
        if r["token"] in seen:
            raise ValueError("duplicate manifest token %r" % r["token"])
        seen[r["token"]] = r
    return rows, seen


def resolve(rows):
    values, errors = {}, []
    for r in rows:
        try:
            src = r["source"].strip()
            table = load(src)
            raw = (csv_lookup(table, r["selector"], src) if src.endswith(".csv")
                   else json_lookup(table, r["selector"].strip(), src))
            values[r["token"]] = fmt(raw, r["format"].strip())
        except Exception as exc:                                   # noqa: BLE001
            errors.append("%s: %s" % (r["token"], exc))
    return values, errors


# ------------------------------------------------------------------ substitution + spans

def substitute(tmpl, values):
    out = []
    spans = []
    pos = 0
    used = set()
    missing = []
    for m in TOKEN_RE.finditer(tmpl):
        out.append(tmpl[pos:m.start()])
        tok = m.group(1)
        if tok not in values:
            missing.append(tok)
            rep = m.group(0)
        else:
            rep = values[tok]
            used.add(tok)
        start = sum(len(x) for x in out)
        out.append(rep)
        if tok in values:
            spans.append((start, start + len(rep), tok))
        pos = m.end()
    out.append(tmpl[pos:])
    return "".join(out), spans, used, missing


# ------------------------------------------------------------------ the digits check

WHITELIST = [
    ("ledger_entry_id", r"\b(?:F|PR|E|P|V|D|R|G|T|S)-\d{3}(?:R)?\b"),
    ("check_or_jc_id", r"\b(?:SK|JC)-\d{1,2}\b"),
    ("packet_id", r"\bW(?:0b|10|[1-9]b?)\b"),
    ("gate_id", r"\bG[01]\b"),
    ("hypothesis_id", r"\bH[123][′']?\b"),
    ("iso_date", r"\b20\d\d-\d\d-\d\d\b"),
    ("section_ref", r"§\s?\d{1,2}(?:\.\d{1,2})?(?:\s?[\u2013-]\s?\d{1,2}(?:\.\d{1,2})?)?"),
    ("md_heading_number", r"(?m)^#{1,6}\s+\d{1,2}(?:\.\d{1,2})*\.?\s"),
    ("md_ordered_list", r"(?m)^\s{0,6}\d{1,2}\.\s"),
    ("md_table_column_rule", r"(?m)^\|[\s\-:|]+\|$"),
    ("item_ref", r"\bitems?\s\d{1,2}[a-z]?(?:\([iv]+\)|\(\w\))?"),
    ("row_ref", r"\brows?\s\d\b"),
    ("clause_ref", r"\bclauses?\s[A-Z]?\d\b"),
    ("model_name", r"Qwen3-8B|Qwen2\.5-14B-Instruct|Qwen2\.5-0\.5B-Instruct|Qwen/Qwen[\w.\-]+"
                   r"|DeepSeek-R1-Distill-(?:Qwen-7B|Llama-8B)|deepseek-ai/[\w.\-]+"
                   r"|gemma-2-9b-it|google/gemma-2-9b-it|claude-sonnet-5|Qwen2\b|Qwen3\b"
                   r"|R1-distills?\b|\bR1\b"),
    ("dtype_or_norm", r"\bbf16\b|\bfp16\b|\bfp32\b|\bint8\b|\bL2\b|\bsha(?:1|256)\b"),
    ("sub_or_superscript", r"[\u2080-\u2089\u00b2\u00b3\u00b9\u2070\u2074-\u2079]+"),
    ("dose_notation", r"α\s*[=∈]\s*[+\u2212-]?\d+(?:\.\d+)?"
                      r"|α\s*∈\s*\{[^}]*\}|±\s?\d+(?:\.\d+)?"
                      r"|\|α\|\s*[≤≥=]\s*\d+(?:\.\d+)?"
                      r"|P\(\s*[+\u2212-]?\d+(?:\.\d+)?\s*\)"
                      r"|(?<![\w.])[+\u2212]\d+(?:\.\d+)?\s+arm\b"),
    ("phat_label", r"p̂\s*=\s*[+\u2212-]?1"),
    ("hardware_name", r"A100(?:-SXM4)?-80\s?GB|A100\sPCIe|H200\sNVL|MacBook\sPro|M5\b"),
    ("upstream_path", r"(?:upstream|src|runs|analysis|writeup)/[\w./*{}\-]+"),
    ("file_or_cmd", r"`[^`\n]*`"),
    ("code_element", r"<code>[^<]*</code>"),
    ("control_label", r"\bCONTROL \d\b"),
    ("svg_axis_tick", r'class="st-[ew]"[^>]*>\s*[\d.]+\s*</text>'),
    ("footnote_marker", r"\[\^\d+\]"),
]
WHITELIST = [(n, re.compile(p)) for n, p in WHITELIST]


MARKUP_RE = re.compile(r"<style\b.*?</style>|<script\b.*?</script>|<[^>]*>", re.S | re.I)


def digits_check(text, spans, is_html=False):
    covered = bytearray(len(text))
    for a, b, _ in spans:
        for i in range(a, b):
            covered[i] = 1
    if is_html:
        # CSS rules and tag attributes are markup, not prose: geometry and colours are not
        # claims. Everything a reader actually sees -- text nodes, including SVG labels --
        # stays inside the check.
        for m in MARKUP_RE.finditer(text):
            for i in range(m.start(), m.end()):
                if text[i].isdigit() and not covered[i]:
                    covered[i] = 2
    wl_hits = {}
    for name, rx in WHITELIST:
        for m in rx.finditer(text):
            hit = False
            for i in range(m.start(), m.end()):
                if text[i].isdigit() and not covered[i]:
                    covered[i] = 2
                    hit = True
            if hit:
                wl_hits[name] = wl_hits.get(name, 0) + 1

    violations = []
    i = 0
    while i < len(text):
        if text[i].isdigit() and covered[i] == 0:
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] in ",._") \
                    and covered[j] == 0:
                j += 1
            line = text.count("\n", 0, i) + 1
            lstart = text.rfind("\n", 0, i) + 1
            lend = text.find("\n", i)
            ctx = text[lstart:lend if lend != -1 else len(text)]
            violations.append((line, text[i:j], ctx.strip()[:160]))
            i = j
        else:
            i += 1

    n_digits = sum(1 for c in text if c.isdigit())
    n_ph = sum(1 for i, c in enumerate(text) if c.isdigit() and covered[i] == 1)
    n_wl = sum(1 for i, c in enumerate(text) if c.isdigit() and covered[i] == 2)
    return {"n_digit_chars": n_digits, "from_placeholder": n_ph, "from_whitelist": n_wl,
            "violations": violations, "whitelist_hits": wl_hits}


# ------------------------------------------------------------------ main

def build():
    rows, _ = read_manifest()
    values, errors = resolve(rows)
    if errors:
        for e in errors:
            print("MANIFEST ERROR  " + e, file=sys.stderr)
        raise SystemExit("%d manifest entries could not be resolved" % len(errors))
    built = []
    used_all = set()
    for tname, oname in TARGETS:
        tpath = os.path.join(HERE, tname)
        if not os.path.exists(tpath):
            continue
        tmpl = open(tpath, encoding="utf-8").read()
        text, spans, used, missing = substitute(tmpl, values)
        used_all |= used
        built.append({"template": tname, "out": oname, "text": text, "spans": spans,
                      "missing": missing, "is_html": oname.endswith(".html")})
    unused = sorted({r["token"] for r in rows} - used_all)
    return rows, values, built, unused


def main():
    rows, values, built, unused = build()

    if "--manifest" in sys.argv:
        for r in rows:
            print("%-38s %-24s %-46s %s" % (r["token"], r["source"],
                                            r["selector"][:46], values[r["token"]]))
        return 0

    if "--verify" in sys.argv:
        rc = 0
        for b in built:
            path = os.path.join(HERE, b["out"])
            on_disk = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            same = on_disk == b["text"]
            print("rebuild identity  %-14s %s (%d bytes)"
                  % (b["out"], "IDENTICAL" if same else "DIFFERS", len(b["text"])))
            rc |= 0 if same else 1
        return rc

    lines = ["no-hand-typed-digits check", "built by: python3 writeup/build.py", "",
             "placeholders in manifest           : %d" % len(rows),
             "tokens never used in any template  : %d%s"
             % (len(unused), (" -> " + ", ".join(unused)) if unused else "")]
    ok = True
    for b in built:
        with open(os.path.join(HERE, b["out"]), "w", encoding="utf-8") as fh:
            fh.write(b["text"])
        rep = digits_check(b["text"], b["spans"], b["is_html"])
        ok = ok and not rep["violations"] and not b["missing"]
        lines += ["", "--- writeup/%s  (from %s)" % (b["out"], b["template"]),
                  "placeholder sites substituted      : %d" % len(b["spans"]),
                  "tokens in template not in manifest : %d%s"
                  % (len(b["missing"]),
                     (" -> " + ", ".join(sorted(set(b["missing"])))) if b["missing"] else ""),
                  "digit characters                   : %d" % rep["n_digit_chars"],
                  "  traceable to a placeholder       : %d" % rep["from_placeholder"],
                  "  covered by a whitelist rule      : %d" % rep["from_whitelist"],
                  "  UNTRACEABLE (violations)         : %d" % len(rep["violations"]),
                  "whitelist rules that fired:"]
        for name, _ in WHITELIST:
            if name in rep["whitelist_hits"]:
                lines.append("  %-22s %4d matches carrying digits"
                             % (name, rep["whitelist_hits"][name]))
        if b["is_html"] and rep["whitelist_hits"].get("html_markup") is None:
            lines.append("  html_markup            (CSS rules and tag attributes excluded)")
        if rep["violations"]:
            lines.append("VIOLATIONS:")
            for ln, frag, ctx in rep["violations"]:
                lines.append("  line %-5d %-14s | %s" % (ln, frag, ctx))
    lines += ["", "RESULT: %s" % ("PASS - every digit in every built document is "
                                  "machine-substituted or structural" if ok else "FAIL")]
    report = "\n".join(lines) + "\n"
    with open(CHECK_OUT, "w") as fh:
        fh.write(report)
    print(report, end="")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
