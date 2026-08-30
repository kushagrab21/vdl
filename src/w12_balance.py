"""W12 Step 2 item 8 / D-039's standing rule: probe every metered service's spendable
balance BEFORE the packet's first spend. Prints only balances, never a credential.

  python3 src/w12_balance.py
"""
import json, os, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import runpod_client as rp


def runpod_balance():
    q = "query { myself { clientBalance currentSpendPerHr } }"
    st, body = rp.graphql(q)
    m = (body.get("data") or {}).get("myself") or {}
    return st, m


def anthropic_probe():
    """One 1-token call to the pinned judge model. Costs a fraction of a cent; a
    too-low balance returns HTTP 400 with 'credit balance is too low'."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        for line in (ROOT.parent / ".env").read_text().splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        return "NO_KEY", None
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": "claude-sonnet-5", "max_tokens": 1,
                         "messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60, context=rp.ctx()) as r:
            return r.status, json.loads(r.read().decode())["usage"]
    except urllib.error.HTTPError as e:
        return e.code, rp.scrub(e.read().decode()[:300])


if __name__ == "__main__":
    st, m = runpod_balance()
    print("RUNPOD   graphql myself -> HTTP %s  clientBalance=$%s  currentSpendPerHr=$%s"
          % (st, m.get("clientBalance"), m.get("currentSpendPerHr")))
    st, u = anthropic_probe()
    print("ANTHROPIC messages(max_tokens=1) -> HTTP %s  %s" % (st, u))
