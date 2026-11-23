"""Regras para ações pedidas por agentes (MCP)."""

from __future__ import annotations

from ..ports import SettingsRepository
from .errors import ConfirmationRequired, PermissionDenied


class AgentGuard:
    def __init__(self, settings: SettingsRepository):
        self.settings = settings

    def require_enabled(self) -> None:
        if not self.settings.load().agents.enabled:
            raise PermissionDenied("Agentes estão desligados no VPN Tray (vpnctl agents enabled on).")

    def check(self, action: str, confirmed: object) -> None:
        """action: 'connect' | 'disconnect'. Exige confirmação explícita."""
        self.require_enabled()
        agents = self.settings.load().agents
        allowed = agents.allow_connect if action == "connect" else agents.allow_disconnect
        if not allowed:
            raise PermissionDenied(
                f"O usuário não permite que agentes {'conectem' if action == 'connect' else 'desconectem'} "
                f"a VPN (vpnctl agents allow-{action} on)."
            )
        if confirmed is not True:
            verb = "conectar" if action == "connect" else "desconectar"
            raise ConfirmationRequired(
                f"Pergunte ao usuário se pode {verb} e chame de novo com user_confirmed=true."
            )
