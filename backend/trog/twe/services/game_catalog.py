CATALOG = {
    "games": [
        {
            "key": "ark_survival_ascended",
            "name": "ARK: Survival Ascended",
            "maps": [
                {
                    "key": "the_island",
                    "name": "The Island",
                }
            ],
        },
        {
            "key": "minecraft_java",
            "name": "Minecraft: Java Edition",
            "maps": [{"key": "curseforge_modpack", "name": "CurseForge modpack"}],
        },
    ]
}


def game_catalog():
    return CATALOG


def resolve_catalog_selection(game_key: str, map_key: str):
    for game in CATALOG["games"]:
        if game["key"] != game_key:
            continue
        for game_map in game["maps"]:
            if game_map["key"] == map_key:
                return game, game_map
    return None, None
