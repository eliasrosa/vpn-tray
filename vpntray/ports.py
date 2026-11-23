"""Portas: o que a aplicação precisa do mundo externo (contratos).

A aplicação só conhece estes Protocols. Implementações reais ficam em
`adapters/` e as de mentira (testes, demo) em `adapters/memory.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from .domain.model import NewProfile, Policy, ProfileMeta, Settings, UnitInfo


class Handle(Protocol):
    def close(self) -> None:
        """Para de acompanhar (encerra o processo/leitura por trás)."""


class ServiceManager(Protocol):
    """Liga/desliga as units vpn-tray@<perfil> e informa o estado."""

    def units(self, profiles: list[str]) -> Mapping[str, UnitInfo]:
        """Estado e InvocationID atuais de cada perfil pedido."""

    def start(self, profile: str) -> None:
        """Inicia a unit. Lança AuthenticationDenied se o polkit recusar; StartFailed se falhar."""

    def stop(self, profile: str) -> None:
        """Para a unit. Lança StartFailed se não conseguir."""


class Journal(Protocol):
    """Leitura do log (síncrona)."""

    def invocation_lines(self, invocation_id: str) -> list[str]:
        """Todas as linhas de uma execução específica da unit."""

    def tail(self, profile: str, lines: int) -> str:
        """Últimas `lines` linhas do log do perfil, com data/hora."""


class JournalFollower(Protocol):
    """Leitura do log ao vivo (precisa de um laço de eventos — usado pelo ícone)."""

    def follow_invocation(self, invocation_id: str, on_line: Callable[[str], None]) -> Handle:
        """Entrega as linhas da execução (desde o início) e as novas, uma a uma."""

    def follow_profile(self, profile: str, on_line: Callable[[str], None]) -> Handle:
        """Entrega as últimas linhas do perfil e as novas (janela "Ver log")."""


class ProfileRepository(Protocol):
    """Perfis visíveis sem privilégio (/etc/openfortivpn/*.args)."""

    def list(self) -> dict[str, ProfileMeta]:
        """Perfis cadastrados, por nome, sem nenhum segredo."""


class ProfileAdmin(Protocol):
    """Ações privilegiadas (helper root via pkexec). Lançam AdminError/AdminCancelled."""

    def add(self, profile: NewProfile) -> None:
        """Grava um perfil novo (.conf 0600 + .args 0644)."""

    def remove(self, name: str) -> None:
        """Para a unit e apaga o .conf e o .args do perfil."""

    def trust(self, name: str, digest: str) -> None:
        """Acrescenta o SHA256 do certificado ao trusted-cert do perfil."""

    def set_require_password(self, enabled: bool) -> None:
        """Liga/desliga a senha ao conectar (regera a regra do polkit)."""


class SettingsRepository(Protocol):
    """Preferências do usuário (~/.config/vpn-tray/settings.json)."""

    def load(self) -> Settings:
        """Configurações atuais (padrões se o arquivo não existir ou for inválido)."""

    def save(self, settings: Settings) -> None:
        """Grava as configurações de forma atômica."""


class PolicyReader(Protocol):
    """Política de segurança do sistema (/etc/vpn-tray/policy.json)."""

    def load(self) -> Policy:
        """Política atual (padrão: não pede senha ao conectar)."""


class Browser(Protocol):
    def open(self, url: str) -> None:
        """Abre a URL no navegador padrão do usuário."""


class NetworkProbe(Protocol):
    """O que se observa da máquina sem privilégio."""

    def ppp_interfaces(self) -> list[str]:
        """Interfaces ppp* existentes."""

    def external_openfortivpn(self) -> bool:
        """openfortivpn rodando fora das units do VPN Tray."""

    def tray_running(self) -> bool:
        """O ícone está aberto? (aí é ele quem abre o navegador no SAML)."""


class Clock(Protocol):
    def now(self) -> float:
        """Tempo monotônico em segundos."""

    def sleep(self, seconds: float) -> None:
        """Espera `seconds` segundos."""
