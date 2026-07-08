import os
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
                values[key.strip()] = value.strip()
    return values

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

def send_rcon_command(command):
    env = load_env()
    host = env.get("RCON_HOST", "127.0.0.1")
    port = int(env.get("RCON_PORT", "27020"))
    password = env.get("RCON_PASSWORD")

    if not password:
        raise RuntimeError("RCON_PASSWORD is missing from .env")

    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(rcon_packet(1, 3, password))
        auth_id, _, _ = read_packet(sock)

        if auth_id == -1:
            raise RuntimeError("RCON authentication failed")

        sock.sendall(rcon_packet(2, 2, command))
        _, _, response = read_packet(sock)

    return response

def list_players():
    response = send_rcon_command("ListPlayers")
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
        players.append(line)
    return players
