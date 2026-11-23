"""Sistema em memória: implementa TODAS as portas, para testes e `--demo`.

Simula o openfortivpn: `start()` agenda as linhas de log de uma conexão SAML
(ou, para o perfil "quebrada", um erro de certificado) que saem a cada
`tick()`. Nada aqui toca no sistema de verdade.
"""

from __future__ import annotations

from collections.abc import Callable

from ..application.errors import AdminError, AuthenticationDenied
from ..domain.model import NewProfile, Policy, ProfileMeta, Settings, UnitInfo
from ..domain.rules import validate_new_profile

BROKEN = "quebrada"


class _Handle:
    def __init__(self):
        self.closed = False

    def close(self) -> None:
        self.closed = True


class MemorySystem:
    def __init__(self, profiles: dict[str, str] | None = None):
        """profiles: {nome: auth}."""
        self._profiles = {
            n: ProfileMeta(n, a, f"vpn.{n}.example") for n, a in (profiles or {"work": "saml"}).items()
        }
        self._units: dict[str, UnitInfo] = {}
        self._lines: dict[str, list[str]] = {}
        self._readers: dict[str, list[Callable[[str], None]]] = {}
        self._script: dict[str, list[str]] = {}
        self._inv = 0
        self.settings_data = Settings()
        self.policy_data = Policy()
        self.calls: list[tuple] = []
        self.opened: list[str] = []
        self.external = False
        self.tray = False
        self.deny_auth = False
        self.time = 0.0

    # ----------------------------------------------------- ServiceManager
    def units(self, profiles: list[str]) -> dict[str, UnitInfo]:
        return {p: self._units.get(p, UnitInfo()) for p in profiles}

    def start(self, profile: str) -> None:
        self.calls.append(("start", profile))
        if self.deny_auth:  # simula a senha recusada no polkit
            raise AuthenticationDenied()
        self._inv += 1
        self._units[profile] = UnitInfo("activating", f"inv{self._inv}")
        if profile == BROKEN:
            self._script[profile] = [
                "ERROR:  Gateway certificate validation failed.",
                "    trusted-cert = " + "ab" * 32,
                "__fail__",
            ]
        else:
            self._script[profile] = [
                "INFO:   Listening for SAML login on port 8020",
                f"INFO:   Authenticate at 'https://vpn.{profile}.example/remote/saml/start?redirect=1'",
                "__active__",
                "INFO:   Authenticated.",
                "INFO:   Tunnel is up and running.",
            ]

    def stop(self, profile: str) -> None:
        self.calls.append(("stop", profile))
        self._script.pop(profile, None)
        if profile in self._units:
            self._units[profile] = UnitInfo("inactive", self._units[profile].invocation_id)

    def tick(self) -> bool:
        """Avança um passo de cada conexão simulada."""
        for name, script in list(self._script.items()):
            if not script:
                del self._script[name]
                continue
            line = script.pop(0)
            unit = self._units[name]
            if line == "__active__":
                self._units[name] = UnitInfo("active", unit.invocation_id)
            elif line == "__fail__":
                self._units[name] = UnitInfo("failed", unit.invocation_id)
            else:
                self._lines.setdefault(unit.invocation_id, []).append(line)
                for cb in self._readers.get(unit.invocation_id, []):
                    cb(line)
        return True

    def run_until(self, profile: str, state: str, steps: int = 10) -> None:
        for _ in range(steps):
            if self._units.get(profile, UnitInfo()).active_state == state and not self._script.get(profile):
                return
            self.tick()

    # ------------------------------------------------- Journal / Follower
    def invocation_lines(self, invocation_id: str) -> list[str]:
        return list(self._lines.get(invocation_id, []))

    def tail(self, profile: str, lines: int) -> str:
        inv = self._units.get(profile, UnitInfo()).invocation_id
        return "\n".join(self._lines.get(inv, ["(sem log ainda)"])[-lines:])

    def follow_invocation(self, invocation_id: str, on_line: Callable[[str], None]) -> _Handle:
        for line in self._lines.get(invocation_id, []):
            on_line(line)
        self._readers.setdefault(invocation_id, []).append(on_line)
        return _Handle()

    def follow_profile(self, profile: str, on_line: Callable[[str], None]) -> _Handle:
        inv = self._units.get(profile, UnitInfo()).invocation_id
        for line in self._lines.get(inv, ["(sem log ainda)"]):
            on_line(line)
        if inv:
            self._readers.setdefault(inv, []).append(on_line)
        return _Handle()

    # --------------------------------------------- ProfileRepository/Admin
    def list(self) -> dict[str, ProfileMeta]:
        return dict(self._profiles)

    def add(self, profile: NewProfile) -> None:
        self.calls.append(("admin", "add", profile.name))
        err = validate_new_profile(profile, self._profiles)
        if err:
            raise AdminError(err)
        self._profiles[profile.name] = ProfileMeta(profile.name, profile.auth, profile.host)

    def remove(self, name: str) -> None:
        self.calls.append(("admin", "remove", name))
        self._profiles.pop(name, None)
        self._units.pop(name, None)

    def trust(self, name: str, digest: str) -> None:
        self.calls.append(("admin", "trust", name, digest))

    def set_require_password(self, enabled: bool) -> None:
        self.calls.append(("admin", "policy", enabled))
        self.policy_data = Policy(enabled)

    # ----------------------------------------------- Settings / Policy
    # (SettingsRepository e PolicyReader têm o mesmo método load(): wrappers)
    @property
    def settings_repo(self) -> _SettingsRepo:
        return _SettingsRepo(self)

    @property
    def policy_reader(self) -> _PolicyReader:
        return _PolicyReader(self)

    # ------------------------------------------- Browser / Probe / Clock
    def open(self, url: str) -> None:
        self.opened.append(url)

    def ppp_interfaces(self) -> list[str]:
        return ["ppp0"] if any(u.active_state == "active" for u in self._units.values()) else []

    def external_openfortivpn(self) -> bool:
        return self.external

    def tray_running(self) -> bool:
        return self.tray

    def now(self) -> float:
        return self.time

    def sleep(self, seconds: float) -> None:
        self.time += seconds
        self.tick()


class _SettingsRepo:
    def __init__(self, system: MemorySystem):
        self.system = system

    def load(self) -> Settings:
        return Settings.from_dict(self.system.settings_data.to_dict())

    def save(self, settings: Settings) -> None:
        self.system.settings_data = Settings.from_dict(settings.to_dict())


class _PolicyReader:
    def __init__(self, system: MemorySystem):
        self.system = system

    def load(self) -> Policy:
        return self.system.policy_data
