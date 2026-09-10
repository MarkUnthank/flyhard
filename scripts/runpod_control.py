#!/usr/bin/env python3
"""Small Runpod v2 client with a bounded, single-Pod pilot lifecycle.

Credentials stay in the local .env, never in command arguments or uploaded code.
Mutations are never retried automatically: reconcile the recorded name first.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = Path(os.environ.get("FLYHARD_SESSION_DIR", str(ROOT / "work"))).resolve()
STATE = SESSION_DIR / "runpod-session.json"


class RunpodError(RuntimeError):
    def __init__(self, status, detail):
        self.status = status
        super().__init__(f"Runpod HTTP {status}: {detail[:1200]}")


def api_key():
    if os.environ.get("RUNPOD_API_KEY"):
        return os.environ["RUNPOD_API_KEY"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip().startswith("RUNPOD_API_KEY="):
            return shlex.split(line.split("=", 1)[1], comments=True)[0]
    raise RuntimeError("RUNPOD_API_KEY missing")


def request(method, path, payload=None):
    key = api_key()
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.runpod.io" + path, data=body, method=method,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 Flyhard/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode().replace(key, "[REDACTED]")
        raise RunpodError(exc.code, detail) from None


def balance():
    # v2 has usage history but no balance endpoint yet.
    r = request("POST", "/graphql", {"query": "query { myself { clientBalance currentSpendPerHr } }"})
    if r.get("errors"):
        raise RuntimeError(str(r["errors"]))
    return r["data"]["myself"]


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n")
    temp.replace(STATE)


def safe_pod(pod):
    return {k: v for k, v in pod.items() if k not in {"env", "registry"}}


def durable_workspace(pod):
    """Return only a real provider-reported network mount at the project root."""
    mounts = pod.get("mounts", {})
    network = mounts.get("network", [])
    if len(network) == 1 and network[0].get("path") == "/workspace":
        return network[0].get("volumeId")
    return None


def release_compute(pod):
    """Network Pods cannot reliably stop; deletion detaches their durable volume."""
    if durable_workspace(pod):
        request("DELETE", "/v2/pods/" + pod["id"])
        return "terminated; network volume retained"
    if pod.get("mounts", {}).get("network"):
        raise RuntimeError("Network Pod has no durable /workspace; refusing automatic deletion")
    request("POST", "/v2/pods/" + pod["id"] + "/action", {"action": "stop"})
    return "stopped; ordinary workspace retained"


def must_stop(state, remaining, now):
    return (now >= state["deadline_epoch"]
            or remaining <= state["reserve_usd"]
            or state["initial_balance_usd"] - remaining >= state["spend_cap_usd"])


def resolve_pod(state):
    if state.get("pod_id"):
        try:
            return request("GET", "/v2/pods/" + state["pod_id"])
        except RunpodError as exc:
            if exc.status == 404:
                return None
            raise
    result = request("GET", "/v2/pods")
    pods = result.get("pods", []) if isinstance(result, dict) else result
    matches = [p for p in pods if p["name"] == state["name"]]
    if len(matches) > 1:
        raise RuntimeError("Duplicate pilot names: explicit reconciliation required")
    return matches[0] if matches else None


def watch():
    """Local independent guard. API outages retry; never create/start resources."""
    failures = 0
    while True:
        state = json.loads(STATE.read_text())
        if state.get("closed"):
            return
        try:
            pod = resolve_pod(state)
            if pod is None:
                if time.time() > state["requested_epoch"] + 900:
                    print("No pilot found after 15 minutes; guard exiting", flush=True)
                    return
                time.sleep(20)
                continue
            current = balance()
            print(json.dumps({"time": time.time(), "pod_id": pod["id"],
                              "status": pod.get("status"), **current}), flush=True)
            if must_stop(state, current["clientBalance"], time.time()) or failures >= 3:
                print("Budget/deadline guard releasing compute", flush=True)
                print(release_compute(pod), flush=True)
                if durable_workspace(pod):
                    if resolve_pod(state) is None:
                        state["closed"] = True
                        state["released_by_guard_epoch"] = time.time()
                        save_state(state)
                        return
                    continue
                check = request("GET", "/v2/pods/" + pod["id"])
                print(json.dumps(safe_pod(check)), flush=True)
                if check.get("status") == "EXITED":
                    return
            failures = 0
        except Exception as exc:
            failures += 1
            print(f"Guard error {failures}: {exc}", flush=True)
            # If balance polling is broken, stop the known pilot conservatively.
            if failures >= 3 and state.get("pod_id"):
                try:
                    known = state.get("created", {"id": state["pod_id"]})
                    release_compute(known)
                except Exception as stop_exc:
                    print(f"Stop retry pending: {stop_exc}", flush=True)
        time.sleep(30)


def launch(config_path):
    config = json.loads(Path(config_path).read_text())
    if STATE.exists() and not json.loads(STATE.read_text()).get("closed"):
        raise RuntimeError("An existing session must be reconciled before any new launch")
    current = balance()
    if current["clientBalance"] < 10:
        raise RuntimeError("Pilot requires at least $10 existing credit; never tops up")
    gpu_id = config["gpu"]["id"]
    if config["gpu"].get("count", 1) != 1:
        raise RuntimeError("First pilot is limited to one GPU")
    catalog = request("GET", "/v2/catalog/gpus/" + urllib.parse.quote(gpu_id, safe=""))
    gpu_price = catalog["price"][config.get("cloud", "SECURE").lower()]
    storage_gb = config.get("disk", 0) + config.get("mounts", {}).get("persistent", {}).get("size", 0)
    estimated_hourly = gpu_price + storage_gb * 0.10 / (30 * 24)
    network_id = durable_workspace(config)
    if config.get("mounts", {}).get("network"):
        if not network_id or config["mounts"].get("persistent"):
            raise RuntimeError("Network runtime requires one durable /workspace and no ordinary volume")
        volume = request("GET", "/v2/network-volumes/" + network_id)
        if volume["type"] != "STANDARD":
            raise RuntimeError("Only STANDARD network-volume pricing is configured")
        config["dataCenterIds"] = [volume["dataCenter"]]
        estimated_hourly += volume["size"] * 0.07 / (30 * 24)
        config.setdefault("env", {})["FLYHARD_NETWORK_VOLUME_ID"] = network_id
    if not 0 < estimated_hourly <= 0.90:
        raise RuntimeError(f"Hourly cost ${estimated_hourly:.3f} exceeds this pilot's $0.90 limit")
    now = time.time()
    state = {"name": config["name"], "requested_epoch": now, "deadline_epoch": now + 6 * 3600,
             "initial_balance_usd": current["clientBalance"], "reserve_usd": 4.0,
             "spend_cap_usd": 6.0, "estimated_hourly_usd": estimated_hourly,
             "network_volume_id": network_id,
             "auto_pay_verified_disabled": config.pop("auto_pay_verified_disabled", None),
             "closed": False}
    save_state(state)
    with (SESSION_DIR / "runpod-guard.log").open("a") as log:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "watch"],
                                stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    state["guard_pid"] = proc.pid
    save_state(state)
    if sys.platform == "darwin":
        subprocess.Popen(["caffeinate", "-i", "-w", str(proc.pid)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    # Supply this project's public key only, without modifying other account keys.
    config.setdefault("env", {})["PUBLIC_KEY"] = (ROOT / "secrets/runpod_ed25519.pub").read_text().strip()
    pod = request("POST", "/v2/pods", config)
    state["pod_id"] = pod["id"]
    state["created"] = safe_pod(pod)
    save_state(state)
    print(json.dumps(safe_pod(pod), indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["balance", "launch", "status", "watch", "stop", "terminate"])
    parser.add_argument("config", nargs="?")
    args = parser.parse_args()
    if args.command == "balance":
        print(json.dumps(balance(), indent=2))
    elif args.command == "launch":
        launch(args.config)
    elif args.command == "watch":
        watch()
    else:
        state = json.loads(STATE.read_text())
        pod = resolve_pod(state)
        if args.command == "status":
            print(json.dumps({"balance": balance(), "pod": safe_pod(pod) if pod else None}, indent=2))
        else:
            if args.command == "terminate" and not state.get("exports_verified") and not (pod and durable_workspace(pod)):
                raise RuntimeError("Verify local exports and record exports_verified before termination")
            if pod:
                if args.command == "stop":
                    print(release_compute(pod))
                else:
                    print(json.dumps(request("DELETE", "/v2/pods/" + pod["id"])))
            if args.command == "terminate" or (pod and durable_workspace(pod)):
                state["closed"] = True
                save_state(state)


if __name__ == "__main__":
    main()
