"""Minimal stdlib-only RunPod client for this project. Never prints the key.

The credential is read from the untracked `../.env` (or the environment), per
standing constraint 3. Nothing here echoes it, and every exception message runs
through `scrub()` before it can reach stdout or the ledger.

Two surfaces are used, because RunPod splits them:
  * REST  `https://rest.runpod.io/v1`   — pods: list, create, stop, terminate.
  * GraphQL `https://api.runpod.io/graphql` — GPU catalogue with live price and
    stock, and the account-level SSH public key setting.
"""

import json
import os
import re
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request

_SRC = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_SRC)
ENV_PATH = os.path.join(os.path.dirname(PROJECT_ROOT), ".env")

REST = "https://rest.runpod.io/v1"
GRAPHQL = "https://api.runpod.io/graphql"

_SECRET_RE = re.compile(r"\b(?:rpa" + r"_)?[A-Za-z0-9_\-]{24,}\b")


def scrub(text):
    """Remove anything key-shaped from a string bound for stdout or an exception."""
    return _SECRET_RE.sub("<redacted>", str(text))


def load_key():
    """RUNPOD_API_KEY from the environment, else from the untracked ../.env."""
    key = os.environ.get("RUNPOD_API_KEY")
    if key:
        return key.strip()
    with open(ENV_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("RUNPOD_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("RUNPOD_API_KEY not in the environment or in " + ENV_PATH)


# --- TLS: this python.org build ships no CA bundle -------------------------

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


_CTX = None


def ctx():
    global _CTX
    if _CTX is None:
        c = ssl.create_default_context()
        try:
            has_ca = c.cert_store_stats().get("x509_ca", 0) > 0
        except Exception:
            has_ca = False
        if not has_ca:
            bundle = _macos_ca_bundle()
            if bundle:
                c.load_verify_locations(cafile=bundle)
        _CTX = c
    return _CTX


# --- requests --------------------------------------------------------------

def _request(url, method, payload=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + load_key(),
        "Content-Type": "application/json",
        # api.runpod.io sits behind Cloudflare, which answers the default
        # "Python-urllib/3.x" agent with 403 / error 1010. A real UA is required.
        "User-Agent": "vdl-runner/1.0 (+https://github.com/kushagrab21/vdl)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx()) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return exc.code, {"error": scrub(body[:800])}
    except urllib.error.URLError as exc:
        raise RuntimeError(scrub("network error: %s" % exc.reason))


def rest(path, method="GET", payload=None, timeout=90):
    return _request(REST + path, method, payload, timeout)


def graphql(query, variables=None, timeout=90):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    return _request(GRAPHQL, "POST", body, timeout)
