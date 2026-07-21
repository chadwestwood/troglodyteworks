from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .nitrado_provider import NitradoProvider
from .pterodactyl_provider import PterodactylHostingProvider
from .self_hosted_provider import SelfHostedProvider


class ProviderNotRegistered(LookupError):
    pass


class ProviderCapabilityUnavailable(LookupError):
    pass


@dataclass(frozen=True)
class ProviderRegistration:
    connection_describer_factory: Callable[[], object] | None = None
    resource_discoverer_factory: Callable[[], object] | None = None
    status_reader_factory: Callable[[], object] | None = None
    provisioning_factory: Callable[[], object] | None = None
    credential_validator_factory: Callable[[], object] | None = None
    credential_resource_discoverer_factory: Callable[[], object] | None = None


class ProviderRegistry:
    def __init__(self):
        self._registrations: dict[str, ProviderRegistration] = {}

    def register(self, provider_key: str, registration: ProviderRegistration):
        if provider_key in self._registrations:
            raise ValueError(f"Provider is already registered: {provider_key}")
        self._registrations[provider_key] = registration

    def connection_describer(self, provider_key: str):
        return self._capability(provider_key, "connection_describer_factory")

    def resource_discoverer(self, provider_key: str):
        return self._capability(provider_key, "resource_discoverer_factory")

    def status_reader(self, provider_key: str):
        return self._capability(provider_key, "status_reader_factory")

    def provisioner(self, provider_key: str):
        return self._capability(provider_key, "provisioning_factory")

    def credential_validator(self, provider_key: str):
        return self._capability(provider_key, "credential_validator_factory")

    def credential_resource_discoverer(self, provider_key: str):
        return self._capability(provider_key, "credential_resource_discoverer_factory")

    def _capability(self, provider_key: str, capability: str):
        registration = self._registrations.get(provider_key)
        if not registration:
            raise ProviderNotRegistered(f"Unsupported provider: {provider_key}")
        factory = getattr(registration, capability)
        if not factory:
            raise ProviderCapabilityUnavailable(
                f"Provider {provider_key} does not support {capability.removesuffix('_factory')}."
            )
        return factory()


def build_provider_registry(config, nitrado_transport=None) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        "self_hosted",
        ProviderRegistration(
            connection_describer_factory=lambda: SelfHostedProvider(config),
            status_reader_factory=lambda: SelfHostedProvider(config),
        ),
    )
    registry.register(
        "pterodactyl",
        ProviderRegistration(
            provisioning_factory=lambda: PterodactylHostingProvider(config),
        ),
    )
    registry.register(
        "nitrado",
        ProviderRegistration(
            connection_describer_factory=lambda: NitradoProvider(config, nitrado_transport),
            status_reader_factory=lambda: NitradoProvider(config, nitrado_transport),
            credential_validator_factory=lambda: NitradoProvider(config, nitrado_transport),
            credential_resource_discoverer_factory=lambda: NitradoProvider(config, nitrado_transport),
        ),
    )
    return registry
