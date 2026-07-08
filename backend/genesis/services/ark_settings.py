from pathlib import Path
import configparser
from knowledge.world_profiles import build_world_profile

BASE = Path("/opt/asa-server/ShooterGame/Saved/Config/WindowsServer")
GAME_USER_SETTINGS = BASE / "GameUserSettings.ini"

WATCHLIST = [
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

def read_ini(path):
    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str
    parser.read(path)
    return parser

def get_server_settings():
    parser = read_ini(GAME_USER_SETTINGS)

    settings = {}
    for key in WATCHLIST:
        if parser.has_section("ServerSettings") and parser.has_option("ServerSettings", key):
            settings[key] = parser.get("ServerSettings", key)
        else:
            settings[key] = None

    return {
        "server": "Cohorts in the Wild -- Genesis",
        "map": "Genesis_WP",
        "source_file": str(GAME_USER_SETTINGS),
        "settings": settings,
        "profile": build_world_profile(settings)
    }
