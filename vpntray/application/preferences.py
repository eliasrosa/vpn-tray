"""Casos de uso: preferências do usuário e política de segurança."""

from __future__ import annotations

from ..domain.model import Settings
from ..ports import PolicyReader, ProfileAdmin, SettingsRepository

AGENT_KEYS = ("enabled", "allow_connect", "allow_disconnect")


class PreferencesService:
    def __init__(self, settings: SettingsRepository, policy: PolicyReader, admin: ProfileAdmin):
        self.settings, self.policy, self.admin = settings, policy, admin

    def load(self) -> Settings:
        return self.settings.load()

    def set_default(self, name: str | None) -> None:
        s = self.settings.load()
        s.default = name
        self.settings.save(s)

    def set_autoconnect(self, enabled: bool) -> None:
        s = self.settings.load()
        s.autoconnect = enabled
        self.settings.save(s)

    def set_agent_permission(self, key: str, value: bool) -> None:
        if key not in AGENT_KEYS:
            raise KeyError(key)
        s = self.settings.load()
        setattr(s.agents, key, value)
        self.settings.save(s)

    def set_require_password(self, enabled: bool) -> None:
        """Muda a regra do polkit (pede senha de admin nos dois sentidos)."""
        self.admin.set_require_password(enabled)
