"""Portas: o que a aplicação precisa do mundo externo (contratos).

A aplicação só conhece estes Protocols. Implementações reais ficam em
`adapters/` e as de mentira (testes, demo) em `adapters/memory.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from .domain.model import NewProfile, Policy, ProfileMeta, Settings, UnitInfo


class Handle(Protocol):
    def close(self) -> None: ...


class ServiceManager(Protocol):
    """Liga/desliga as units vpn-tray@<perfil> e informa o estado."""

    def units(self, profiles: list[str]) -> Mapping[str, UnitInfo]: ...

    def start(self, profile: str) -> None:
        """Lança AuthenticationDenied se o polkit recusar; StartFailed se falhar."""

    def stop(self, profile: str) -> None: ...


class Journal(Protocol):
    """Leitura do log (síncrona)."""

    def invocation_lines(self, invocation_id: str) -> list[str]: ...

    def tail(self, profile: str, lines: int) -> str: ...


class JournalFollower(Protocol):
    """Leitura do log ao vivo (precisa de um laço de eventos — usado pelo ícone)."""

    def follow_invocation(self, invocation_id: str, on_line: Callable[[str], None]) -> Handle: ...

    def follow_profile(self, profile: str, on_line: Callable[[str], None]) -> Handle: ...


class ProfileRepository(Protocol):
    """Perfis visíveis sem privilégio (/etc/openfortivpn/*.args)."""

    def list(self) -> dict[str, ProfileMeta]: ...


class ProfileAdmin(Protocol):
    """Ações privilegiadas (helper root via pkexec). Lançam AdminError."""

    def add(self, profile: NewProfile) -> None: ...

    def remove(self, name: str) -> None: ...

    def trust(self, name: str, digest: str) -> None: ...

    def set_require_password(self, enabled: bool) -> None: ...


class SettingsRepository(Protocol):
    def load(self) -> Settings: ...

    def save(self, settings: Settings) -> None: ...


class PolicyReader(Protocol):
    def load(self) -> Policy: ...


class Browser(Protocol):
    def open(self, url: str) -> None: ...


class NetworkProbe(Protocol):
    def ppp_interfaces(self) -> list[str]: ...

    def external_openfortivpn(self) -> bool:
        """openfortivpn rodando fora das units do VPN Tray."""

    def tray_running(self) -> bool:
        """O ícone está aberto? (aí é ele quem abre o navegador no SAML)."""


class Clock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...
