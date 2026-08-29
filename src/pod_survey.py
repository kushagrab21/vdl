"""W0b Step 3, read-only half: what GPUs are available and what do they cost.

Spends nothing. Queries the RunPod GPU catalogue, applies the owner-approved
envelope (A100 80GB, on-demand, at or under $2.20/hr) and prints the qualifying
offers; if none qualify it prints the three cheapest options with at least 48 GB
of VRAM, which is the fallback report the W0b order asks for.

Run:  python3 src/pod_survey.py
"""

import json
import sys
from pathlib import Path

import runpod_client as rp

ENVELOPE_MAX_USD_HR = 2.20
ENVELOPE_MIN_VRAM_GB = 80
FALLBACK_MIN_VRAM_GB = 48

QUERY = """
query GpuTypes {
  gpuTypes {
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    lowestPrice(input: {gpuCount: 1}) {
      minimumBidPrice
      uninterruptablePrice
      stockStatus
    }
  }
}
"""

OUT = Path(__file__).resolve().parent.parent / "analysis" / "out" / "w0b_gpu_survey.json"


def rows():
    status, body = rp.graphql(QUERY)
    if status != 200 or not body or "data" not in body:
        print("GPU catalogue query failed. HTTP", status)
        print(json.dumps(body, indent=2)[:1500] if body else "(no body)")
        sys.exit(1)
    out = []
    for g in body["data"]["gpuTypes"]:
        lp = g.get("lowestPrice") or {}
        out.append({
            "id": g["id"],
            "name": g.get("displayName") or g["id"],
            "vram_gb": g.get("memoryInGb"),
            "secure": bool(g.get("secureCloud")),
            "community": bool(g.get("communityCloud")),
            "on_demand_usd_hr": lp.get("uninterruptablePrice"),
            "spot_usd_hr": lp.get("minimumBidPrice"),
            "stock": lp.get("stockStatus"),
        })
    return out


def line(r):
    price = r["on_demand_usd_hr"]
    return "  %-34s %5s GB  on-demand %-9s stock=%-12s %s" % (
        r["name"], r["vram_gb"],
        ("$%.2f/hr" % price) if price else "n/a",
        r["stock"] or "unknown",
        ("secure" if r["secure"] else "") + ("+community" if r["community"] else ""))


def main():
    all_rows = rows()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_rows, indent=2))
    print("catalogue entries     :", len(all_rows))
    print("saved                 :", OUT)

    priced = [r for r in all_rows if r["on_demand_usd_hr"]]
    in_stock = [r for r in priced if (r["stock"] or "").lower() not in ("none", "", "null")]

    a100_80 = [r for r in in_stock
               if (r["vram_gb"] or 0) >= ENVELOPE_MIN_VRAM_GB
               and "a100" in r["name"].lower()
               and r["on_demand_usd_hr"] <= ENVELOPE_MAX_USD_HR]
    a100_80.sort(key=lambda r: r["on_demand_usd_hr"])

    print("\n=== ENVELOPE: A100 80GB, on-demand, <= $%.2f/hr, in stock ===" % ENVELOPE_MAX_USD_HR)
    if a100_80:
        for r in a100_80:
            print(line(r))
        print("\nCHEAPEST QUALIFYING:", a100_80[0]["id"],
              "at $%.2f/hr" % a100_80[0]["on_demand_usd_hr"])
    else:
        print("  NONE QUALIFY.")
        fallback = [r for r in in_stock if (r["vram_gb"] or 0) >= FALLBACK_MIN_VRAM_GB]
        fallback.sort(key=lambda r: r["on_demand_usd_hr"])
        print("\n=== FALLBACK: three cheapest in-stock options with >= %d GB VRAM ==="
              % FALLBACK_MIN_VRAM_GB)
        for r in fallback[:3]:
            print(line(r))

    print("\n=== all A100/H100-class entries seen (for context) ===")
    for r in sorted(priced, key=lambda r: r["on_demand_usd_hr"]):
        if any(k in r["name"].lower() for k in ("a100", "h100", "h200", "a6000", "l40")):
            print(line(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
