"""Composição: o único lugar que escolhe os adaptadores concretos.

`build()` monta os casos de uso com o sistema de verdade; `build_memory()`
com o sistema em memória (testes e `--demo`). Variáveis de ambiente
VPN_TRAY_CONF_DIR / VPN_TRAY_SETTINGS / VPN_TRAY_POLICY trocam os caminhos
(usadas pelos testes de ponta a ponta).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .adapters.desktop import LinuxNetworkProbe, SystemClock, XdgBrowser
from .adapters.filesystem import (
    DEFAULT_CONF_DIR,
    DEFAULT_POLICY_FILE,
    EtcProfileRepository,
    JsonPolicyReader,
    JsonSettingsRepository,
)
from .adapters.memory import MemorySystem
from .adapters.pkexec import PkexecProfileAdmin
from .adapters.systemd import JournalctlJournal, SystemdServiceManager
from .application.agent_guard import AgentGuard
from .application.connection import ConnectionService
from .application.preferences import PreferencesService
from .application.profiles import ProfileService
from .application.status import StatusService
from .ports import (
    Browser,
    Clock,
    Journal,
    NetworkProbe,
    PolicyReader,
    ProfileAdmin,
    ProfileRepository,
    ServiceManager,
    SettingsRepository,
)


@dataclass
class Container:
    profiles_repo: ProfileRepository
    services: ServiceManager
    journal: Journal
    settings: SettingsRepository
    policy: PolicyReader
    admin: ProfileAdmin
    browser: Browser
    probe: NetworkProbe
    clock: Clock

    def __post_init__(self):
        self.status = StatusService(
            self.profiles_repo, self.services, self.journal, self.settings, self.policy, self.probe
        )
        self.connection = ConnectionService(self.status, self.services, self.browser, self.probe, self.clock)
        self.profiles = ProfileService(self.profiles_repo, self.admin, self.settings)
        self.preferences = PreferencesService(self.settings, self.policy, self.admin)
        self.guard = AgentGuard(self.settings)


def build() -> Container:
    return Container(
        profiles_repo=EtcProfileRepository(os.environ.get("VPN_TRAY_CONF_DIR", DEFAULT_CONF_DIR)),
        services=SystemdServiceManager(),
        journal=JournalctlJournal(),
        settings=JsonSettingsRepository(os.environ.get("VPN_TRAY_SETTINGS") or None),
        policy=JsonPolicyReader(os.environ.get("VPN_TRAY_POLICY", DEFAULT_POLICY_FILE)),
        admin=PkexecProfileAdmin(),
        browser=XdgBrowser(),
        probe=LinuxNetworkProbe(),
        clock=SystemClock(),
    )


def build_memory(system: MemorySystem | None = None) -> Container:
    s = system or MemorySystem()
    c = Container(
        profiles_repo=s,
        services=s,
        journal=s,
        settings=s.settings_repo,
        policy=s.policy_reader,
        admin=s,
        browser=s,
        probe=s,
        clock=s,
    )
    c.system = s  # type: ignore[attr-defined]
    return c
