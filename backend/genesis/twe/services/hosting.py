from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InstanceSpec:
    instance_id: str
    community_id: str
    game_key: str
    map_key: str
    name: str


@dataclass(frozen=True)
class ProviderInstanceState:
    provider_instance_id: str
    provider_status: str
    detail: str | None = None


class HostingProvider(Protocol):
    def create_instance(self, spec: InstanceSpec) -> ProviderInstanceState:
        raise NotImplementedError

    def get_instance_status(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError

    def start_instance(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError

    def stop_instance(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError

    def restart_instance(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError
