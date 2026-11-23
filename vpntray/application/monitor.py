"""Caso de uso do ícone: acompanhar as conexões ao vivo.

Independente de GTK: quem chama `poll()` periodicamente é o laço de eventos
do ícone (ou um teste). Eventos emitidos para `on_event(kind, profile, data)`:

    "auth"    data=url     login SAML começou (abrir navegador)
    "cert"    data=sha256  certificado não confiável
    "up"      data=None    túnel no ar
    "failed"  data=erro    a unit falhou
    "down"    data=None    desconectou (estava no ar)
    "changed" data=None    qualquer mudança (redesenhar)

Só execuções que começaram depois do primeiro poll são "ao vivo": as que já
estavam rodando quando o monitor abriu são relidas sem disparar eventos.
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain.model import Policy, ProfileMeta, SessionInfo, State, UnitInfo
from ..domain.openfortivpn import LogSession
from ..domain.rules import first_with, is_running, overall_state, profile_state
from ..ports import JournalFollower, NetworkProbe, PolicyReader, ProfileRepository, ServiceManager

EventHandler = Callable[[str, str, object], None]


class ConnectionMonitor:
    def __init__(
        self,
        profiles: ProfileRepository,
        services: ServiceManager,
        policy: PolicyReader,
        probe: NetworkProbe,
        follower: JournalFollower,
        on_event: EventHandler,
    ):
        self._profiles, self._services, self._policy = profiles, services, policy
        self._probe, self._follower, self._on_event = probe, follower, on_event
        self.profiles: dict[str, ProfileMeta] = {}
        self.units: dict[str, UnitInfo] = {}
        self.policy = Policy()
        self.sessions: dict[str, LogSession] = {}
        self.finished: dict[str, LogSession] = {}
        self._started_by_us: set[str] = set()
        self._first_poll_done = False

    # ------------------------------------------------------------- leitura
    def poll(self) -> None:
        self.profiles = self._profiles.list()
        self.units = dict(self._services.units(list(self.profiles)))
        self.policy = self._policy.load()
        for name, unit in self.units.items():
            running = is_running(unit.active_state)
            sess = self.sessions.get(name)
            if running and unit.invocation_id and (sess is None or sess.invocation != unit.invocation_id):
                if sess:
                    sess.close()
                live = name in self._started_by_us or self._first_poll_done
                self._started_by_us.discard(name)
                sess = LogSession(name, unit.invocation_id, live, self._session_event)
                self.sessions[name] = sess
                self.finished.pop(name, None)
                sess.handle = self._follower.follow_invocation(unit.invocation_id, sess.feed)
            elif not running and sess is not None:
                sess.close()
                del self.sessions[name]
                self.finished[name] = sess
                if unit.active_state == "failed":
                    self._on_event("failed", name, sess.info.last_error)
                elif sess.info.tunnel_up:
                    self._on_event("down", name, None)
        for gone in set(self.sessions) - set(self.profiles):
            self.sessions.pop(gone).close()
        self._first_poll_done = True
        self._on_event("changed", "", None)

    def _session_event(self, kind: str, sess: LogSession) -> None:
        data = {"auth": sess.info.auth_url, "cert": sess.info.untrusted_cert}.get(kind)
        self._on_event(kind, sess.profile, data)

    def state_of(self, name: str) -> State:
        unit = self.units.get(name, UnitInfo())
        sess = self.sessions.get(name)
        return profile_state(unit.active_state, bool(sess and sess.info.tunnel_up))

    def states(self) -> dict[str, State]:
        return {n: self.state_of(n) for n in self.profiles}

    def info(self, name: str) -> SessionInfo | None:
        sess = self.sessions.get(name) or self.finished.get(name)
        return sess.info if sess else None

    def external(self, states: dict[str, State] | None = None) -> bool:
        states = states if states is not None else self.states()
        return (
            not any(s in (State.ON, State.CONNECTING) for s in states.values())
            and self._probe.external_openfortivpn()
        )

    def overall(self) -> State:
        states = self.states()
        return overall_state(states, self.external(states))

    def waiting_login(self) -> bool:
        name = first_with(self.states(), State.CONNECTING)
        info = self.info(name) if name else None
        return bool(info and info.auth_url and not info.tunnel_up)

    def active(self) -> list[str]:
        return [n for n, s in self.states().items() if s in (State.ON, State.CONNECTING)]

    # --------------------------------------------------------------- ações
    def connect(self, name: str) -> None:
        """Derruba outra VPN ativa e inicia `name` (pode bloquear na senha)."""
        for other in self.active():
            if other != name:
                self._services.stop(other)
        self.finished.pop(name, None)
        self._started_by_us.add(name)
        self._services.start(name)

    def disconnect(self, name: str) -> None:
        self._services.stop(name)
