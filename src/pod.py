"""Pod lifecycle tool for this project: register key, create, status, stop, terminate.

One tool rather than one script per action, because R-004 makes stop-at-packet-close a
standing obligation and every future GPU packet needs the same four verbs.

  python3 src/pod.py register-key          # Step 2: account-level SSH public key
  python3 src/pod.py images                # which runpod/pytorch tags actually exist
  python3 src/pod.py create --gpu "NVIDIA A100 80GB PCIe" --max-price 2.20
  python3 src/pod.py status [POD_ID]
  python3 src/pod.py stop POD_ID           # halts billing, keeps the volume
  python3 src/pod.py terminate POD_ID      # destroys the pod and its volume

The credential never appears in argv, stdout, or any error message.
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.request

import runpod_client as rp

PUBKEY_PATH = os.path.expanduser("~/.ssh/id_ed25519_runpod.pub")

# Envelope defaults (owner-approved, W0b Step 3).
DEFAULT_VOLUME_GB = 100
DEFAULT_CONTAINER_GB = 60
# Verified to exist on Docker Hub via `python3 src/pod.py images` before first use —
# the obvious-looking runpod/pytorch:2.4.0-…-ubuntu22.04 tag does NOT exist. CUDA 12.8 +
# torch 2.8 matches what current vLLM wheels are built against, so vLLM's install does
# not drag in a second multi-GB torch.
DEFAULT_IMAGE = "runpod/pytorch:1.2.0-rc.162-cu1281-torch280-ubuntu2204"

# The container command. RunPod injects the account's SSH keys as $PUBLIC_KEY; this
# installs them, starts sshd, and blocks so the container stays alive.
#
# Every step is separated by ';', never '&&', and `sleep infinity` is unconditional.
# An earlier version chained on '&&': the sshd binary was missing, the chain broke,
# bash exited, and the pod billed with a dead container. The container must outlive
# any single failed step so it can be inspected rather than silently costing money.
KEEPALIVE_SSH = (
    "bash -c 'mkdir -p /root/.ssh; echo \"$PUBLIC_KEY\" >> /root/.ssh/authorized_keys; "
    "chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
    "(apt-get update -qq; apt-get install -y -qq openssh-server) >/dev/null 2>&1; "
    "mkdir -p /run/sshd; ssh-keygen -A >/dev/null 2>&1; "
    "/usr/sbin/sshd -D >/var/log/sshd.log 2>&1 & "
    "sleep infinity'")


# --------------------------------------------------------------------------
# Step 2 — SSH public key on the account
# --------------------------------------------------------------------------

def cmd_register_key(args):
    with open(PUBKEY_PATH, "r", encoding="utf-8") as fh:
        pub = fh.read().strip()

    status, body = rp.graphql("query { myself { id pubKey } }")
    if status != 200 or not body or not body.get("data"):
        print("could not read account settings. HTTP", status)
        print(json.dumps(body, indent=2)[:800] if body else "(no body)")
        return 1
    current = (body["data"]["myself"].get("pubKey") or "").strip()

    if pub in current:
        print("already registered  : yes (account pubKey already contains this key)")
        print("fingerprint         :", _fingerprint())
        return 0

    # Append rather than replace — the account field holds every key as one
    # newline-separated blob, and clobbering it would lock out the owner's others.
    merged = (current + "\n" + pub).strip() if current else pub
    status, body = rp.graphql(
        "mutation Reg($in: UpdateUserSettingsInput!) { updateUserSettings(input: $in) { id pubKey } }",
        {"in": {"pubKey": merged}})
    if status != 200 or not body or not body.get("data"):
        print("registration failed. HTTP", status)
        print(json.dumps(body, indent=2)[:800] if body else "(no body)")
        return 1

    got = (body["data"]["updateUserSettings"].get("pubKey") or "")
    print("registration        :", "OK" if pub in got else "MUTATION RETURNED WITHOUT OUR KEY")
    print("keys on account now :", len([l for l in got.splitlines() if l.strip()]))
    print("fingerprint         :", _fingerprint())
    print("method              : account-level (GraphQL updateUserSettings.pubKey),"
          " injected into every pod")
    return 0 if pub in got else 1


def _fingerprint():
    out = subprocess.run(["ssh-keygen", "-lf", PUBKEY_PATH], capture_output=True, text=True)
    return out.stdout.strip() or "(unavailable)"


# --------------------------------------------------------------------------
# Image tags — verify rather than guess
# --------------------------------------------------------------------------

def cmd_images(args):
    """List runpod/pytorch tags from Docker Hub. No RunPod credential is sent."""
    url = ("https://hub.docker.com/v2/repositories/runpod/pytorch/tags"
           "?page_size=100&ordering=last_updated")
    req = urllib.request.Request(url, headers={"User-Agent": "vdl-runner/1.0"})
    with urllib.request.urlopen(req, timeout=60, context=rp.ctx()) as resp:
        data = json.loads(resp.read().decode())
    # Cosign signature tags (sha256-….sig) dominate the listing and are not runnable.
    names = [t["name"] for t in data.get("results", [])
             if not t["name"].startswith("sha256-")]
    print("runpod/pytorch runnable tags (newest first):")
    for n in names[:40]:
        print("  ", n)
    # Match "-rc." specifically: a bare "rc" substring hits every tag, via "torch".
    stable = [n for n in names if "-rc." not in n]
    print("\nnon-rc (stable) tags:", stable[:10] or "(none on this page)")
    print("\ndefault in this tool:", DEFAULT_IMAGE)
    print("default exists      :", DEFAULT_IMAGE.split(":", 1)[1] in names)
    return 0


# --------------------------------------------------------------------------
# Step 3 — create
# --------------------------------------------------------------------------

CREATE = """
mutation Deploy($in: PodFindAndDeployOnDemandInput!) {
  podFindAndDeployOnDemand(input: $in) {
    id
    name
    imageName
    machineId
    costPerHr
    desiredStatus
    volumeInGb
    containerDiskInGb
    machine { podHostId gpuDisplayName }
  }
}
"""


def cmd_create(args):
    if args.max_price is not None and args.price_check:
        # Re-confirm the live price sits inside the envelope before spending.
        status, body = rp.graphql(
            'query { gpuTypes { id displayName lowestPrice(input: {gpuCount: 1})'
            ' { uninterruptablePrice stockStatus } } }')
        if status == 200 and body and body.get("data"):
            match = [g for g in body["data"]["gpuTypes"] if g["id"] == args.gpu]
            if match:
                lp = match[0].get("lowestPrice") or {}
                live = lp.get("uninterruptablePrice")
                print("live on-demand price:", ("$%.2f/hr" % live) if live else "n/a",
                      "| stock:", lp.get("stockStatus"))
                if live and live > args.max_price:
                    print("REFUSING: $%.2f/hr exceeds the envelope's $%.2f/hr."
                          % (live, args.max_price))
                    return 2

    payload = {
        "cloudType": args.cloud,
        "gpuCount": 1,
        "gpuTypeId": args.gpu,
        "name": args.name,
        "imageName": args.image,
        "volumeInGb": args.volume_gb,
        "containerDiskInGb": args.container_gb,
        "volumeMountPath": "/workspace",
        "ports": "22/tcp",
        "startSsh": True,
        "minVcpuCount": 8,
        "minMemoryInGb": 50,
        "supportPublicIp": True,
    }
    if args.docker_args:
        # Without this the 1.2.x runpod/pytorch images start, find no long-running
        # command, and exit — the pod bills while its container is dead. This is the
        # standard RunPod pattern: install the injected PUBLIC_KEY, start sshd, block.
        payload["dockerArgs"] = args.docker_args
    print("creating pod with    :", json.dumps(
        {k: v for k, v in payload.items()}, indent=2))
    status, body = rp.graphql(CREATE, {"in": payload})
    if status != 200 or not body or not body.get("data") or not body["data"].get(
            "podFindAndDeployOnDemand"):
        print("CREATE FAILED. HTTP", status)
        print(json.dumps(body, indent=2)[:1500] if body else "(no body)")
        return 1
    pod = body["data"]["podFindAndDeployOnDemand"]
    print("\n=== POD CREATED ===")
    print(json.dumps(pod, indent=2))
    print("\npod id              :", pod["id"])
    print("cost per hour       : $%s" % pod.get("costPerHr"))
    return 0


# --------------------------------------------------------------------------
# status / stop / terminate
# --------------------------------------------------------------------------

def cmd_status(args):
    path = "/pods/" + args.pod_id if args.pod_id else "/pods"
    status, body = rp.rest(path)
    print("HTTP", status)
    print(json.dumps(body, indent=2)[:4000] if body else "(no body)")
    return 0 if status == 200 else 1


def cmd_wait(args):
    """Poll until the pod reports a public IP and a mapped SSH port."""
    import time
    for attempt in range(args.tries):
        status, body = rp.rest("/pods/" + args.pod_id)
        if status != 200 or not body:
            print("poll HTTP", status)
            time.sleep(args.every)
            continue
        ip = body.get("publicIp") or ""
        pm = body.get("portMappings") or {}
        rt = body.get("runtime") or {}
        print("[%02d] desired=%s ip=%s portMappings=%s uptime=%s"
              % (attempt, body.get("desiredStatus"), ip or "-", pm or "-",
                 rt.get("uptimeInSeconds") if rt else "-"))
        if ip and pm.get("22"):
            print("\nREADY")
            print("ssh -i ~/.ssh/id_ed25519_runpod -p %s root@%s" % (pm["22"], ip))
            return 0
        time.sleep(args.every)
    print("\nnot ready after %d polls" % args.tries)
    return 1


def cmd_stop(args):
    status, body = rp.rest("/pods/%s/stop" % args.pod_id, method="POST")
    print("stop HTTP", status)
    print(json.dumps(body, indent=2)[:2000] if body else "(no body)")
    s2, b2 = rp.rest("/pods/" + args.pod_id)
    print("\npost-stop desiredStatus:",
          (b2 or {}).get("desiredStatus"), "| HTTP", s2)
    return 0 if status in (200, 201) else 1


def cmd_terminate(args):
    if not args.yes:
        print("refusing: pass --yes to confirm destruction of the pod and its volume")
        return 2
    status, body = rp.rest("/pods/" + args.pod_id, method="DELETE")
    print("terminate HTTP", status)
    print(json.dumps(body, indent=2)[:1000] if body else "(no body)")
    return 0 if status in (200, 204) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("register-key").set_defaults(fn=cmd_register_key)
    sub.add_parser("images").set_defaults(fn=cmd_images)

    c = sub.add_parser("create")
    c.add_argument("--gpu", required=True)
    c.add_argument("--name", default="vdl")
    c.add_argument("--image", default=DEFAULT_IMAGE)
    c.add_argument("--cloud", default="ALL", choices=["ALL", "SECURE", "COMMUNITY"])
    c.add_argument("--volume-gb", type=int, default=DEFAULT_VOLUME_GB)
    c.add_argument("--container-gb", type=int, default=DEFAULT_CONTAINER_GB)
    c.add_argument("--max-price", type=float, default=None)
    c.add_argument("--docker-args", default=KEEPALIVE_SSH,
                   help="container command; default installs PUBLIC_KEY, starts sshd, blocks")
    c.add_argument("--price-check", action="store_true", default=True)
    c.set_defaults(fn=cmd_create)

    s = sub.add_parser("status")
    s.add_argument("pod_id", nargs="?")
    s.set_defaults(fn=cmd_status)

    w = sub.add_parser("wait")
    w.add_argument("pod_id")
    w.add_argument("--every", type=int, default=15)
    w.add_argument("--tries", type=int, default=24)
    w.set_defaults(fn=cmd_wait)

    p = sub.add_parser("stop")
    p.add_argument("pod_id")
    p.set_defaults(fn=cmd_stop)

    t = sub.add_parser("terminate")
    t.add_argument("pod_id")
    t.add_argument("--yes", action="store_true")
    t.set_defaults(fn=cmd_terminate)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
