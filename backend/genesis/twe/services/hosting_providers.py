from .pterodactyl_provider import PterodactylHostingProvider


def provider_for(name: str, config):
    if name == "pterodactyl":
        return PterodactylHostingProvider(config)
    raise ValueError(f"Unsupported hosting provider: {name}")
