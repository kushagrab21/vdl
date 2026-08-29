"""Extract the RunPod API key from the owner's PDF into `../.env`, without leaking it.

Owner-directed (W0b Step 0), closing out D-002. The key value is never printed,
logged, returned to stdout, or placed in an exception message. This script's only
evidence of success is an HTTP status code from one authenticated RunPod call.

Method, adapted from the working reference at
`Experiment_binding_agent/binding-feedback-experiment/phase3_advisory/providers.py`
(`_extract_key_from_pdf`), which solved the harder case on this same machine:

  1. plain text — the token sits verbatim in the file or in a FlateDecode'd stream;
  2. fallback — Google-Docs-export PDFs use Type0/CIDFontType2 fonts whose content
     stream shows glyphs as hex codes, so a raw read yields garbage. Rebuild the
     ToUnicode CMap (beginbfchar / beginbfrange) and decode the hex show-strings
     through it to recover the visible text, then match the token in that.

Run:  python3 src/extract_runpod_key.py
"""

import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zlib

# Assembled by concatenation so no key-shaped literal appears in tracked source.
_PREFIX = "rpa" + "_"
_KEY_RE = re.compile(re.escape(_PREFIX) + r"[A-Za-z0-9_\-]{16,}")
_KEY_RE_BYTES = re.compile(re.escape(_PREFIX.encode()) + rb"[A-Za-z0-9_\-]{16,}")
# Last-resort shape for a key that carries no recognisable prefix.
_GENERIC_RE = re.compile(r"\b[A-Za-z0-9]{32,}\b")

_SRC = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_SRC)                       # .../vdl
PARENT = os.path.dirname(PROJECT_ROOT)                     # .../SPAR_take_home
PDF_PATH = os.path.join(PARENT, "api_key", "runpod_api.pdf")
ENV_PATH = os.path.join(PARENT, ".env")

RUNPOD_REST = "https://rest.runpod.io/v1/pods"


def _scrub(text):
    """Strip any key-shaped token from a string bound for stdout or an exception."""
    return _GENERIC_RE.sub("<redacted>", _KEY_RE.sub("<redacted>", str(text)))


# --------------------------------------------------------------------------
# PDF text recovery
# --------------------------------------------------------------------------

def _streams(data):
    """Every stream in the PDF, FlateDecode'd where possible."""
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        s = m.end()
        e = data.find(b"endstream", s)
        if e == -1:
            continue
        chunk = data[s:e]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        elif chunk.endswith(b"\n"):
            chunk = chunk[:-1]
        try:
            chunk = zlib.decompress(chunk)
        except Exception:
            pass
        out.append(chunk)
    return out


def _hex_to_unicode(dst_hex):
    """A ToUnicode target (UTF-16BE hex) -> the unicode string it denotes."""
    try:
        return bytes.fromhex(dst_hex.decode("ascii")).decode("utf-16-be")
    except Exception:
        return ""


def _decode_hex_show(hex_bytes, cmap):
    """Decode one PDF hex show-string (2-byte codes) through a ToUnicode cmap."""
    hs = hex_bytes.decode("ascii")
    if len(hs) % 4:
        hs = hs.rjust(((len(hs) + 3) // 4) * 4, "0")
    return "".join(cmap.get(int(hs[i:i + 4], 16), "") for i in range(0, len(hs), 4))


def _build_cmap(streams):
    cmap = {}
    for blob in streams:
        if b"beginbfchar" not in blob and b"beginbfrange" not in blob:
            continue
        for seg in re.findall(rb"beginbfchar(.*?)endbfchar", blob, re.DOTALL):
            for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", seg):
                cmap[int(src, 16)] = _hex_to_unicode(dst)
        for seg in re.findall(rb"beginbfrange(.*?)endbfrange", blob, re.DOTALL):
            for lo, hi, dst in re.findall(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", seg
            ):
                base = int(dst, 16)
                for i in range(int(hi, 16) - int(lo, 16) + 1):
                    cmap[int(lo, 16) + i] = chr(base + i)
    return cmap


def _match(text, method):
    """Return (key, method) for the first key-shaped token in `text`, else None."""
    m = _KEY_RE.search(text)
    if m:
        return m.group(0), method + "/prefixed"
    # The PDFs wrap long keys across lines; retry with whitespace stripped.
    joined = re.sub(r"\s+", "", text)
    m = _KEY_RE.search(joined)
    if m:
        return m.group(0), method + "/prefixed-unwrapped"
    return None


def extract_key():
    """Recover the key from the PDF. Returns (key, method_name). Never prints it."""
    with open(PDF_PATH, "rb") as fh:
        data = fh.read()

    if data[:4] != b"%PDF":
        hit = _match(data.decode("utf-8", "replace"), "plaintext")
        if hit:
            return hit
        raise RuntimeError("key file is not a PDF and holds no key-shaped token")

    streams = _streams(data)

    # 1) Plain text first, per the order.
    for blob in streams + [data]:
        m = _KEY_RE_BYTES.search(blob)
        if m:
            return m.group(0).decode("ascii"), "plaintext/stream"
    for blob in streams + [data]:
        hit = _match(blob.decode("latin-1"), "plaintext")
        if hit:
            return hit

    # 2) Fallback: ToUnicode CMap + hex show-strings.
    cmap = _build_cmap(streams)
    if not cmap:
        raise RuntimeError("no key-shaped token in plain text and no ToUnicode CMap present")

    parts = []
    for blob in streams:
        if b"BT" not in blob:
            continue
        for hx in re.findall(rb"<([0-9A-Fa-f]+)>", blob):
            parts.append(_decode_hex_show(hx, cmap))
    text = "".join(parts)

    hit = _match(text, "cmap")
    if hit:
        return hit

    # 3) Last resort: a long alnum run with no recognisable prefix.
    cands = _GENERIC_RE.findall(re.sub(r"\s+", "", text))
    if cands:
        return max(cands, key=len), "cmap/generic-longest"

    raise RuntimeError("could not locate a key-shaped token in the PDF")


# --------------------------------------------------------------------------
# TLS (this python.org build ships no CA bundle)
# --------------------------------------------------------------------------

def _macos_ca_bundle():
    cache = os.path.join(tempfile.gettempdir(), "vdl_macos_ca.pem")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        return cache
    parts = []
    for kc in ("/System/Library/Keychains/SystemRootCertificates.keychain",
               "/Library/Keychains/System.keychain"):
        if not os.path.exists(kc):
            continue
        try:
            out = subprocess.run(["/usr/bin/security", "find-certificate", "-a", "-p", kc],
                                 capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        if out.returncode == 0 and out.stdout.strip():
            parts.append(out.stdout)
    if not parts:
        return None
    with open(cache, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return cache


def _ssl_context():
    ctx = ssl.create_default_context()
    try:
        has_ca = ctx.cert_store_stats().get("x509_ca", 0) > 0
    except Exception:
        has_ca = False
    if not has_ca:
        bundle = _macos_ca_bundle()
        if bundle:
            ctx.load_verify_locations(cafile=bundle)
    return ctx


# --------------------------------------------------------------------------
# .env + verification
# --------------------------------------------------------------------------

def write_env(key):
    """Append RUNPOD_API_KEY to ../.env (0600). Returns a status word."""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as fh:
            existing = fh.read()
        if re.search(r"^RUNPOD_API_KEY=", existing, re.M):
            return "already-present-left-untouched"
        sep = "" if (existing.endswith("\n") or not existing) else "\n"
        with open(ENV_PATH, "a", encoding="utf-8") as fh:
            fh.write(sep + "RUNPOD_API_KEY=" + key + "\n")
        os.chmod(ENV_PATH, 0o600)
        return "appended"
    fd = os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("RUNPOD_API_KEY=" + key + "\n")
    return "created-0600"


def verify(key):
    """One authenticated RunPod call. Returns (HTTP status, response byte count)."""
    req = urllib.request.Request(
        RUNPOD_REST, method="GET",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45, context=_ssl_context()) as resp:
            return resp.status, len(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body_len = len(exc.read())
        except Exception:
            body_len = -1
        return exc.code, body_len
    except urllib.error.URLError as exc:
        raise RuntimeError(_scrub("network error: %s" % exc.reason))


def main():
    try:
        key, method = extract_key()
    except Exception as exc:
        print("EXTRACTION FAILED:", _scrub(exc))
        return 1

    # Shape report only — length and prefix presence, never the value.
    print("extraction method     :", method)
    print("token length          :", len(key))
    print("carries RunPod prefix :", key.startswith(_PREFIX))

    print("env write             :", write_env(key))
    print("env path              :", ENV_PATH)
    print("env mode              :", oct(os.stat(ENV_PATH).st_mode & 0o777))

    try:
        status, nbytes = verify(key)
    except Exception as exc:
        print("VERIFICATION FAILED:", _scrub(exc))
        return 1
    print("verification endpoint : GET " + RUNPOD_REST)
    print("HTTP status           :", status)
    print("response bytes        :", nbytes)
    return 0 if status == 200 else 2


if __name__ == "__main__":
    sys.exit(main())
