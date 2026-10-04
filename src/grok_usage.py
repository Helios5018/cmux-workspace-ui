#!/usr/bin/env python3
"""Read Grok subscription usage and publish it to a cmux-sentinel meter.

Billing protocol/parser adapted from CC Switch v3.20.1 subscription_grok.rs
(MIT, see ../LICENSE-CC-Switch). Credentials stay in Grok CLI's auth.json.
"""
import argparse
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig"
LABEL = "grokcredits"
from sentinel_config import CMUX, USAGE_STATE as STATE, each_cmux_socket
from sidebar_metadata import stamp


class UsageError(Exception):
    pass


def read_token_once():
    auth_dir = Path.home() / ".grok"
    settings = Path.home() / ".cc-switch/settings.json"
    if settings.exists():
        config = json.loads(settings.read_text())
        if config.get("grokConfigDir"):
            auth_dir = Path(config["grokConfigDir"]).expanduser()
    try:
        auth = json.loads((auth_dir / "auth.json").read_text())
    except FileNotFoundError:
        raise UsageError("login missing; run grok login") from None
    except (ValueError, OSError):
        raise UsageError("cannot read Grok credentials") from None
    if not isinstance(auth, dict):
        raise UsageError("invalid Grok credential format")
    oidc, legacy = [], []
    for scope, value in sorted(auth.items()):
        if not isinstance(value, dict) or not isinstance(value.get("key"), str) or not value["key"]:
            continue
        if scope.startswith("https://auth.x.ai::"):
            oidc.append(value)
        elif "/sign-in" in scope:
            legacy.append(value)
    candidates = oidc or legacy
    if not candidates:
        raise UsageError("login missing; run grok login")
    # Match CC Switch's preference; allow the server to judge expiry/clock skew.
    return candidates[-1]["key"]


def read_token():
    # Grok login can briefly remove/replace credentials. Retry local reads only;
    # never repeat a billing request or turn a missing login into a zero quota.
    for attempt in range(4):
        try:
            return read_token_once()
        except UsageError:
            if attempt == 3:
                raise
            time.sleep(2)


def varint(data, pos):
    value = 0
    for shift in range(0, 64, 7):
        if pos >= len(data):
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, pos
    raise ValueError("invalid varint")


def scan_proto(data, path=(), depth=0):
    floats, ints = [], []
    pos = 0
    while pos < len(data):
        start = pos
        try:
            key, pos = varint(data, pos)
            if key >> 3 == 0:
                raise ValueError("invalid tag")
            field = path + (key >> 3,)
            wire = key & 7
            if wire == 0:
                value, pos = varint(data, pos)
                ints.append((field, value))
            elif wire == 1:
                if pos + 8 > len(data):
                    break
                pos += 8
            elif wire == 2:
                size, pos = varint(data, pos)
                if size > len(data) - pos:
                    raise ValueError("truncated message")
                if depth < 4:
                    fs, vs = scan_proto(data[pos:pos + size], field, depth + 1)
                    floats.extend(fs)
                    ints.extend(vs)
                pos += size
            elif wire == 5:
                if pos + 4 > len(data):
                    break
                floats.append((field, struct.unpack_from("<f", data, pos)[0]))
                pos += 4
            else:
                raise ValueError("unsupported wire type")
        except ValueError:
            pos = start + 1
    return floats, ints


def frames(data):
    payloads, trailers = [], {}
    pos = 0
    while pos < len(data):
        if pos + 5 > len(data):
            return [], {}
        flag, size = data[pos], int.from_bytes(data[pos + 1:pos + 5], "big")
        pos += 5
        if pos + size > len(data):
            return [], {}
        payload = data[pos:pos + size]
        pos += size
        if flag & 128:
            for line in payload.decode("utf-8", errors="replace").splitlines():
                key, sep, value = line.partition(":")
                if sep:
                    trailers[key.strip().lower()] = urllib.parse.unquote(value.strip())
        elif flag == 0:
            payloads.append(payload)
        else:
            raise UsageError("unsupported compressed billing response")
    return payloads, trailers


def check_grpc(headers):
    status = str(headers.get("grpc-status", "0"))
    if status == "0":
        return
    message = headers.get("grpc-message", "").lower()
    if status == "16" or status == "7" and any(x in message for x in ("bad-credentials", "unauthenticated", "token")):
        raise UsageError("login expired; run grok login")
    if status == "9" and "no personal team" in message:
        raise UsageError("team usage unavailable")
    if status in ("1", "4", "14"):
        raise UsageError("billing temporarily unavailable")
    # Never print server bodies/messages, which may contain account details.
    raise UsageError("billing rejected request (gRPC " + status[:4] + ")")


def parse_billing(data, now):
    payloads, trailers = frames(data)
    check_grpc(trailers)
    if not payloads and data and data[0] >> 3 and data[0] & 7 in (0, 1, 2, 5):
        payloads = [data]
    if not payloads:
        raise UsageError("unrecognized billing response")
    floats, ints = [], []
    for payload in payloads:
        fs, vs = scan_proto(payload)
        floats.extend(fs)
        ints.extend(vs)
    percents = [(path, value) for path, value in floats
                if path[-1] == 1 and math.isfinite(value) and 0 <= value <= 100]
    resets = [(path, value) for path, value in ints
              if 1700000000 <= value <= 2100000000 and value > now]
    preferred = [value for path, value in resets if path == (1, 5, 1)]
    reset = min(preferred or [value for _, value in resets], default=None)
    period = any(path[:2] == (1, 6) or path == (1, 8, 1) and value in (1, 2)
                 for path, value in ints)
    if percents:
        used = min(percents, key=lambda x: len(x[0]))[1]
    elif not floats and reset is not None and period:
        used = 0.0
    else:
        raise UsageError("usage format changed; no reliable percentage")
    return {"provider": "grok", "used_percent": round(used, 2), "resets_at": reset,
            "queried_at": int(now), "source": "CC Switch Grok billing protocol"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError("unexpected billing redirect")


def fetch_usage():
    req = urllib.request.Request(ENDPOINT, data=bytes(5), headers={
        "Authorization": "Bearer " + read_token(), "Origin": "https://grok.com",
        "Referer": "https://grok.com/?_s=usage", "Accept": "*/*",
        "Content-Type": "application/grpc-web+proto", "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1", "User-Agent": "cc-switch",
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            check_grpc(response.headers)
            data = response.read(1048577)
            if len(data) > 1048576:
                raise UsageError("oversized billing response")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise UsageError("login rejected (HTTP %d)" % exc.code) from None
        raise UsageError("billing HTTP %d" % exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UsageError("billing network unavailable") from None
    return parse_billing(data, time.time())


def cmux(*args):
    result = subprocess.run([CMUX, *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise UsageError("cmux command failed: " + args[0])
    return result.stdout


def resolve():
    windows = json.loads(cmux("list-windows", "--json"))
    found = []
    for window in windows:
        win = window.get("ref") or window["id"]
        workspaces = json.loads(cmux("workspace", "list", "--window", win, "--json"))["workspaces"]
        for w in workspaces:
            if w["title"] == LABEL or w["title"].startswith(LABEL + " "):
                found.append((w["ref"], win))
    return found


def countdown(reset):
    if reset is None:
        return "reset unknown"
    minutes = max(0, int(reset - time.time()) // 60)
    if minutes >= 1440:
        return "%dd %dh" % (minutes // 1440, minutes % 1440 // 60)
    return "%dh %dm" % (minutes // 60, minutes % 60)


def atomic_state(name, value):
    STATE.mkdir(parents=True, exist_ok=True)
    temp = STATE / (name + ".tmp." + str(os.getpid()))
    temp.write_text(value)
    temp.chmod(0o600)
    temp.replace(STATE / name)


def publish(snapshot=None, error=None):
    def write():
        targets = resolve()
        if not targets:
            raise UsageError("Grok meter workspace missing")
        for ref, win in targets:
            target = ["--workspace", ref, "--window", win]
            if snapshot is not None:
                percent = snapshot["used_percent"]
                detail = "%g%% (%s)" % (percent, countdown(snapshot["resets_at"]))
                cmux("rename-workspace", *target, LABEL + " |" + detail + "|")
                cmux("set-progress", str(percent / 100), "--label", detail, *target)
            else:
                cmux("rename-workspace", *target, LABEL + " |⚠ " + str(error) + "|")
                cmux("clear-progress", *target)
        if snapshot is not None:
            stamp((LABEL,), snapshot["queried_at"])
            atomic_state("grok.json", json.dumps(snapshot, indent=2) + "\n")
            atomic_state("grok.last-success", str(int(time.time())) + "\n")

    each_cmux_socket(write)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = fetch_usage()
        if args.update:
            publish(snapshot)
        print(json.dumps(snapshot))
        return 0
    except (UsageError, ValueError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc) if isinstance(exc, UsageError) else "local usage reader failed"
        if args.update:
            try:
                publish(error=error)
            except (UsageError, ValueError, OSError, subprocess.SubprocessError):
                pass
        print(json.dumps({"provider": "grok", "error": error}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
