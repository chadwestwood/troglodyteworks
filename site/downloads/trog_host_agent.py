#!/usr/bin/env python3
"""Trog Host Agent: outbound-only, read-only discovery for owned game hosts."""
import argparse
import json
import os
from pathlib import Path
import platform
import socket
import struct
import subprocess
import time
import urllib.request

VERSION = "0.1.0"
CONFIG = Path.home() / ".trog-host-agent.json"


def request_json(url, payload, secret=None):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": f"TrogHostAgent/{VERSION}"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read())


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def read_varint(stream):
    value = 0
    for shift in range(0, 35, 7):
        byte = stream.recv(1)
        if not byte:
            raise OSError("short Minecraft response")
        value |= (byte[0] & 0x7f) << shift
        if not byte[0] & 0x80:
            return value
    raise OSError("invalid Minecraft response")


def minecraft_status(host, port):
    with socket.create_connection((host, port), timeout=2) as stream:
        host_bytes = host.encode()
        handshake = varint(0) + varint(765) + varint(len(host_bytes)) + host_bytes + struct.pack(">H", port) + varint(1)
        stream.sendall(varint(len(handshake)) + handshake + b"\x01\x00")
        read_varint(stream)
        read_varint(stream)
        length = read_varint(stream)
        raw = bytearray()
        while len(raw) < length:
            raw.extend(stream.recv(length - len(raw)))
        return json.loads(raw)


def read_properties(path):
    values = {}
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def minecraft_resources(roots):
    found = []
    seen = set()
    for root in roots:
        base = Path(root).expanduser().resolve()
        candidates = [base / "server.properties"] if base.is_dir() else []
        if base.is_dir():
            candidates.extend(base.glob("*/server.properties"))
        for properties_path in candidates:
            if properties_path in seen or not properties_path.is_file():
                continue
            seen.add(properties_path)
            props = read_properties(properties_path)
            port = int(props.get("server-port", "25565") or 25565)
            status = "offline"
            players, version = [], "unknown"
            try:
                report = minecraft_status("127.0.0.1", port)
                status = "online"
                players = [p.get("name", "") for p in report.get("players", {}).get("sample", []) if p.get("name")]
                version = report.get("version", {}).get("name", "unknown")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            directory = properties_path.parent
            jars = sorted((directory / "mods").glob("*.jar")) if (directory / "mods").is_dir() else []
            loader = "vanilla"
            names = " ".join(path.name.lower() for path in directory.glob("*.jar"))
            for candidate in ("neoforge", "forge", "fabric", "quilt"):
                if candidate in names:
                    loader = candidate
                    break
            found.append({
                "external_id": f"minecraft:{directory}",
                "name": props.get("motd") or directory.name or "Minecraft Server",
                "game_key": "minecraft_java", "status": status,
                "metadata": {"path": str(directory), "port": port, "version": version,
                             "loader": loader, "players": players,
                             "mods": [{"id": jar.stem, "name": jar.stem} for jar in jars[:500]]},
            })
    return found


def ark_resources():
    try:
        output = subprocess.run(["ps", "-ax", "-o", "command="], capture_output=True, text=True, timeout=3, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        output = ""
    commands = [line for line in output.splitlines() if "ArkAscendedServer" in line and "trog_host_agent" not in line]
    return [{"external_id": f"asa:process:{index}", "name": "ARK: Survival Ascended",
             "game_key": "ark_survival_ascended", "status": "online",
             "metadata": {"players": [], "mods": [], "detection": "local_process"}}
            for index, _command in enumerate(commands, 1)]


def discover(roots):
    return ark_resources() + minecraft_resources(roots)


def save_config(value):
    CONFIG.write_text(json.dumps(value, indent=2))
    os.chmod(CONFIG, 0o600)


def pair(args):
    data = request_json(f"{args.site.rstrip('/')}/api/v1/host-agents/pair", {
        "token": args.token, "name": args.name, "platform": platform.platform(), "version": VERSION,
    })
    save_config({"site": args.site.rstrip("/"), "agent_id": data["agent"]["id"],
                 "secret": data["agent"]["secret"], "roots": args.root})
    print("Paired. The credential is stored locally with owner-only permissions.")


def heartbeat(config):
    resources = discover(config.get("roots") or [str(Path.cwd())])
    request_json(f"{config['site']}/api/v1/host-agents/{config['agent_id']}/heartbeat", {
        "platform": platform.platform(), "version": VERSION, "resources": resources,
        "metadata": {"outbound_only": True},
    }, config["secret"])
    print(f"Reported {len(resources)} discovered game server(s).")


def run(args):
    config = json.loads(CONFIG.read_text())
    while True:
        try:
            heartbeat(config)
        except Exception as exc:
            print(f"Heartbeat failed: {exc}")
        if args.once:
            return
        time.sleep(max(30, args.interval))


def main():
    parser = argparse.ArgumentParser(description="Pair a self-hosted game computer with Trog.")
    sub = parser.add_subparsers(dest="command", required=True)
    pairing = sub.add_parser("pair")
    pairing.add_argument("--site", required=True)
    pairing.add_argument("--token", required=True)
    pairing.add_argument("--name", default=platform.node() or "Trog Host")
    pairing.add_argument("--root", action="append", default=[str(Path.cwd())], help="Folder containing a Minecraft server")
    running = sub.add_parser("run")
    running.add_argument("--once", action="store_true")
    running.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    pair(args) if args.command == "pair" else run(args)


if __name__ == "__main__":
    main()
