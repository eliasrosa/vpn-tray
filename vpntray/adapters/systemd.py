"""Adaptador systemd/journald (systemctl, journalctl)."""

from __future__ import annotations

from collections.abc import Callable

from ..application.errors import AuthenticationDenied, StartFailed
from ..domain.model import UnitInfo
from ..domain.rules import unit_name
from .process import run

PREFIX, SUFFIX = "vpn-tray@", ".service"


def parse_unit_show(out: str) -> dict[str, UnitInfo]:
    """Saída de `systemctl show -p Id,ActiveState,InvocationID u1 u2 …`."""
    result: dict[str, UnitInfo] = {}
    cur: dict[str, str] = {}
    for line in [*out.splitlines(), ""]:
        if not line.strip():
            uid = cur.get("Id", "")
            if uid.startswith(PREFIX) and uid.endswith(SUFFIX):
                result[uid[len(PREFIX) : -len(SUFFIX)]] = UnitInfo(
                    cur.get("ActiveState", "inactive"), cur.get("InvocationID", "")
                )
            cur = {}
            continue
        k, _, v = line.partition("=")
        cur[k] = v
    return result


def _auth_failure(err: str) -> bool:
    low = err.lower()
    return "authentic" in low or "autentica" in low or "interactive authentication" in low


class SystemdServiceManager:
    def __init__(self, runner: Callable = run):
        self._run = runner

    def units(self, profiles: list[str]) -> dict[str, UnitInfo]:
        if not profiles:
            return {}
        r = self._run(
            ["systemctl", "show", "-p", "Id,ActiveState,InvocationID"] + [unit_name(p) for p in profiles]
        )
        return parse_unit_show(r.out) if r.ok else {}

    def start(self, profile: str) -> None:
        # Timeout longo: com a política "pedir senha", o polkit espera o usuário.
        r = self._run(["systemctl", "start", unit_name(profile)], timeout=180)
        if not r.ok:
            if _auth_failure(r.err):
                raise AuthenticationDenied()
            raise StartFailed(r.err or f"systemctl start saiu com {r.code}")

    def stop(self, profile: str) -> None:
        r = self._run(["systemctl", "stop", unit_name(profile)], timeout=60)
        if not r.ok:
            raise StartFailed(r.err or f"systemctl stop saiu com {r.code}")


class JournalctlJournal:
    def __init__(self, runner: Callable = run):
        self._run = runner

    def invocation_lines(self, invocation_id: str) -> list[str]:
        if not invocation_id:
            return []
        r = self._run(["journalctl", f"_SYSTEMD_INVOCATION_ID={invocation_id}", "-o", "cat", "--no-pager"])
        return r.out.splitlines()

    def tail(self, profile: str, lines: int) -> str:
        r = self._run(
            ["journalctl", "-u", unit_name(profile), "-n", str(lines), "-o", "short-iso", "--no-pager"]
        )
        return r.out or r.err
