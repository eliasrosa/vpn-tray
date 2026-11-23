"""Caso de uso: retrato do estado das VPNs (CLI e MCP)."""

from __future__ import annotations

from ..domain.model import SessionInfo, State
from ..domain.openfortivpn import summarize
from ..domain.rules import overall_state, profile_state, unit_name
from ..ports import Journal, NetworkProbe, PolicyReader, ProfileRepository, ServiceManager, SettingsRepository


class StatusService:
    def __init__(
        self,
        profiles: ProfileRepository,
        services: ServiceManager,
        journal: Journal,
        settings: SettingsRepository,
        policy: PolicyReader,
        probe: NetworkProbe,
    ):
        self.profiles, self.services, self.journal = profiles, services, journal
        self.settings, self.policy, self.probe = settings, policy, probe

    def get(self) -> dict:
        settings = self.settings.load()
        metas = self.profiles.list()
        units = self.services.units(list(metas))
        result: dict = {
            "profiles": {},
            "default": None,
            "overall": State.OFF.value,
            "ppp": self.probe.ppp_interfaces(),
            "external_openfortivpn": False,
            "policy": {"require_password_connect": self.policy.load().require_password_connect},
            "agents": settings.agents.to_dict(),
        }
        states: dict[str, State] = {}
        for name, meta in metas.items():
            unit = units.get(name)
            active = unit.active_state if unit else "inactive"
            info = (
                summarize(self.journal.invocation_lines(unit.invocation_id))
                if unit and active in ("active", "activating", "failed")
                else SessionInfo()
            )
            st = profile_state(active, info.tunnel_up)
            states[name] = st
            result["profiles"][name] = {
                "state": st.value,
                "label": st.label,
                "unit": unit_name(name),
                "systemd": active,
                "auth": meta.auth,
                "host": meta.host,
                "waiting_browser_login": bool(
                    info.auth_url and not info.tunnel_up and st == State.CONNECTING
                ),
                "login_url": info.auth_url if st == State.CONNECTING else None,
                "untrusted_cert": info.untrusted_cert,
                "last_error": info.last_error if st == State.ERROR else None,
            }
        result["default"] = settings.default if settings.default in metas else next(iter(metas), None)
        external = (
            not any(s in (State.ON, State.CONNECTING) for s in states.values())
            and self.probe.external_openfortivpn()
        )
        result["external_openfortivpn"] = external
        result["overall"] = overall_state(states, external).value
        return result

    def active_profiles(self, status: dict | None = None) -> list[str]:
        status = status or self.get()
        return [
            n for n, p in status["profiles"].items() if p["state"] in (State.ON.value, State.CONNECTING.value)
        ]
