#!/usr/bin/env python3
from pathlib import Path
import configparser
import json

BASE = Path("/opt/asa-server/ShooterGame/Saved/Config/WindowsServer")
GUS = BASE / "GameUserSettings.ini"
GAME = BASE / "Game.ini"

WATCHLIST = {
    "GameUserSettings.ini": {
        "ServerSettings": [
            "MaxPlayers",
            "DifficultyOffset",
            "OverrideOfficialDifficulty",
            "XPMultiplier",
            "TamingSpeedMultiplier",
            "HarvestAmountMultiplier",
            "BabyMatureSpeedMultiplier",
            "EggHatchSpeedMultiplier",
            "MatingIntervalMultiplier",
            "BabyCuddleIntervalMultiplier",
            "AutoSavePeriodMinutes",
            "PlayerCharacterWaterDrainMultiplier",
            "PlayerCharacterFoodDrainMultiplier",
            "DinoCharacterFoodDrainMultiplier",
            "ItemStackSizeMultiplier",
            "RCONEnabled",
            "RCONPort",
        ]
    }
}

def read_ini(path):
    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str
    parser.read(path)
    return parser

def get_setting(parser, section, key):
    if parser.has_section(section) and parser.has_option(section, key):
        return parser.get(section, key)
    return None

def main():
    parser = read_ini(GUS)

    summary = {
        "server": "Cohorts in the Wild -- Genesis",
        "map": "Genesis_WP",
        "source_file": str(GUS),
        "settings": {}
    }

    for section, keys in WATCHLIST["GameUserSettings.ini"].items():
        for key in keys:
            summary["settings"][key] = get_setting(parser, section, key)

    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
