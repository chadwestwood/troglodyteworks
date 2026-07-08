def rating_label(value, ranges):
    if value is None:
        return {
            "label": "Unknown",
            "stars": 0,
            "description": "This setting was not found in the current configuration."
        }

    try:
        value = float(value)
    except ValueError:
        return {
            "label": "Unknown",
            "stars": 0,
            "description": f"Could not interpret value: {value}"
        }

    for upper, label, stars, description in ranges:
        if value <= upper:
            return {
                "label": label,
                "stars": stars,
                "description": description
            }

    return ranges[-1][1]


def describe_harvesting(value):
    return rating_label(value, [
        (1, "Official", 1, "Players gather resources at official server speed."),
        (2, "Slow Casual", 2, "Resource gathering is slightly easier while still feeling survival-focused."),
        (5, "Weekend Casual", 4, "Players gather quickly enough for limited play sessions without making every project trivial."),
        (10, "Fast Build", 5, "Players can build and recover quickly with much less grind."),
        (999, "Creative Style", 5, "Harvesting is extremely fast and survival pressure is greatly reduced.")
    ])


def describe_taming(value):
    return rating_label(value, [
        (1, "Official", 1, "Taming takes official-length time and requires significant planning."),
        (3, "Patient Casual", 3, "Taming is faster but still feels like an investment."),
        (6, "Weekend Friendly", 4, "Most common tames become realistic for evening or weekend play."),
        (15, "Fast Taming", 5, "Players can build a stable of creatures quickly."),
        (999, "Instant-ish", 5, "Taming is extremely fast and removes most waiting.")
    ])


def describe_breeding(value):
    return rating_label(value, [
        (1, "Official", 1, "Breeding follows official timing and requires long-term planning."),
        (10, "Light Boost", 2, "Breeding is easier but still slow."),
        (50, "Fast Breeding", 4, "Breeding is practical for casual communities."),
        (150, "Very Fast", 5, "Babies mature quickly and breeding becomes easy to experiment with."),
        (999, "Breeder Lab", 5, "Breeding is extremely accelerated.")
    ])


def describe_difficulty(value):
    return rating_label(value, [
        (1, "Low Difficulty", 1, "Wild creatures are easier and lower level."),
        (3, "Moderate", 3, "The world has some danger but remains approachable."),
        (5, "Official Max", 4, "The world supports wild dinos up to roughly level 150."),
        (999, "Extreme", 5, "The world is tuned beyond common official-style difficulty.")
    ])


def build_world_profile(settings):
    return {
        "harvesting": describe_harvesting(settings.get("HarvestAmountMultiplier")),
        "taming": describe_taming(settings.get("TamingSpeedMultiplier")),
        "baby_mature": describe_breeding(settings.get("BabyMatureSpeedMultiplier")),
        "egg_hatch": describe_breeding(settings.get("EggHatchSpeedMultiplier")),
        "difficulty": describe_difficulty(settings.get("OverrideOfficialDifficulty")),
    }
