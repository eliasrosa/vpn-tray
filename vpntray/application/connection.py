"""Casos de uso: conectar e desconectar (CLI e MCP; o ícone usa o monitor)."""

from __future__ import annotations

from collections.abc import Callable

from ..domain.model import State
from ..domain.rules import pick_profile
from ..ports import Browser, Clock, NetworkProbe, ServiceManager
from .errors import NotFound
from .status import StatusService


class ConnectionService:
    def __init__(
        self,
        status: StatusService,
        services: ServiceManager,
        browser: Browser,
        probe: NetworkProbe,
        clock: Clock,
    ):
        self.status, self.services, self.browser = status, services, browser
        self.probe, self.clock = probe, clock

    def resolve(self, requested: str | None, *, active: bool = False) -> str:
        st = self.status.get()
        try:
            return pick_profile(
                requested, st["profiles"], st["default"], self.status.active_profiles(st) if active else None
            )
        except LookupError as e:
            raise NotFound(str(e)) from None

    def connect(
        self,
        requested: str | None = None,
        *,
        wait: float = 120,
        open_browser: bool = True,
        on_login_url: Callable[[str], None] | None = None,
    ) -> dict:
        """Conecta (derrubando outra VPN ativa) e espera subir até `wait` s.

        Com SAML, abre o navegador se o ícone não estiver rodando (ele mesmo
        abre quando está). Devolve o status final do perfil.
        """
        name = self.resolve(requested)
        st = self.status.get()
        if st["profiles"][name]["state"] == State.ON.value:
            return {"profile": name, **st["profiles"][name], "already": True}
        for other in self.status.active_profiles(st):
            if other != name:
                self.services.stop(other)
        self.services.start(name)  # AuthenticationDenied / StartFailed sobem
        if not wait:
            return {"profile": name, "state": State.CONNECTING.value, "started": True}

        tray = self.probe.tray_running()

        def login(url: str) -> None:
            if open_browser and not tray:
                self.browser.open(url)
            if on_login_url:
                on_login_url(url)

        final = self._wait(name, wait, login)
        return {"profile": name, **final}

    def disconnect(self, requested: str | None = None) -> str:
        name = self.resolve(requested, active=True)
        self.services.stop(name)
        return name

    def _wait(self, name: str, timeout: float, on_login: Callable[[str], None], poll: float = 1.0) -> dict:
        start = self.clock.now()
        announced = False
        while True:
            p = self.status.get()["profiles"].get(name, {})
            state = p.get("state")
            if state in (State.ON.value, State.ERROR.value):
                return p
            if state == State.OFF.value and self.clock.now() - start > 3:
                return p  # parou logo depois de iniciar
            if p.get("login_url") and not announced:
                announced = True
                on_login(p["login_url"])
            if self.clock.now() - start >= timeout:
                return p
            self.clock.sleep(poll)
