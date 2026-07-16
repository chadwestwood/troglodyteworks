import os
import re
import socket
import struct
from pathlib import Path

ENV_PATH = Path("/srv/troglodyteworks/backend/genesis/.env")

def load_env():
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = clean_env_value(value.strip())
    return values

def clean_env_value(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

def rcon_packet(request_id, packet_type, body):
    payload = body.encode("utf-8") + b"\x00\x00"
    size = len(payload) + 8
    return struct.pack("<iii", size, request_id, packet_type) + payload

def read_packet(sock):
    size_data = sock.recv(4)
    if not size_data:
        raise RuntimeError("No response from RCON server")

    size = struct.unpack("<i", size_data)[0]
    data = b""
    while len(data) < size:
        data += sock.recv(size - len(data))

    request_id, packet_type = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, body

def send_rcon_command(command, host=None, port=None, password=None):
    env = load_env()
    host = host or env.get("TWE_ASA_RCON_HOST") or env.get("RCON_HOST", "127.0.0.1")
    port = int(port or env.get("TWE_ASA_RCON_PORT") or env.get("RCON_PORT", "27020"))
    password = password or env.get("TWE_ASA_RCON_PASSWORD") or env.get("RCON_PASSWORD")

    if not password:
        raise RuntimeError("RCON password is missing from environment configuration")

    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(rcon_packet(1, 3, password))
        auth_id, _, _ = read_packet(sock)

        if auth_id == -1:
            raise RuntimeError("RCON authentication failed")

        sock.sendall(rcon_packet(2, 2, command))
        _, _, response = read_packet(sock)

    return response

def list_players(host=None, port=None, password=None):
    response = send_rcon_command("ListPlayers", host=host, port=port, password=password)
    return {
        "raw": response,
        "players": parse_players(response)
    }

def parse_players(response):
    players = []
    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower() in {"no players connected", "no players connected."}:
            continue
        players.append(parse_player_name(line))
    return players


def parse_player_name(line):
    """Remove the RCON row number and immutable platform ID from ListPlayers."""
    numbered = re.match(r"^\d+\.\s*(.*)$", line.strip())
    entry = numbered.group(1).strip() if numbered else line.strip()
    name, separator, identifier = entry.rpartition(",")
    if separator and re.fullmatch(r"[A-Za-z0-9:_-]{8,}", identifier.strip()):
        return name.strip()
    return entry
