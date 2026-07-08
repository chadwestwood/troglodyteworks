#!/usr/bin/env python3
from pathlib import Path
import configparser
import json

BASE = Path("/opt/asa-server/ShooterGame/Saved/Config/WindowsServer")

FILES = {
    "GameUserSettings.ini": BASE / "GameUserSettings.ini",
    "Game.ini": BASE / "Game.ini",
}

def read_ini(path):
    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str
    parser.read(path)
    return {
        section: dict(parser.items(section))
        for section in parser.sections()
    }

result = {}

for name, path in FILES.items():
    if path.exists():
        result[name] = read_ini(path)
    else:
        result[name] = {"error": f"File not found: {path}"}

print(json.dumps(result, indent=2))
