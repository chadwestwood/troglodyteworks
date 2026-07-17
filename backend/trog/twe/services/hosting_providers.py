from .provider_registry import build_provider_registry


def provider_for(name: str, config):
    return build_provider_registry(config).provisioner(name)
