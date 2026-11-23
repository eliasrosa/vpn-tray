"""Adaptadores de área de trabalho e de sistema (navegador, rede, relógio)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from .process import run

TRAY_DBUS_NAME = "br.local.vpntray"


class XdgBrowser:
    def __init__(self, runner: Callable = run):
        self._run = runner

    def open(self, url: str) -> None:
        self._run(["xdg-open", url], timeout=10)


class LinuxNetworkProbe:
    def __init__(self, sys_net: str = "/sys/class/net", proc: str = "/proc", runner: Callable = run):
        self.sys_net, self.proc, self._run = sys_net, proc, runner

    def ppp_interfaces(self) -> list[str]:
        try:
            return sorted(n for n in os.listdir(self.sys_net) if n.startswith("ppp"))
        except OSError:
            return []

    def external_openfortivpn(self) -> bool:
        try:
            pids = [p for p in os.listdir(self.proc) if p.isdigit()]
        except OSError:
            return False
        for pid in pids:
            try:
                with open(f"{self.proc}/{pid}/comm") as f:
                    if f.read().strip() != "openfortivpn":
                        continue
                with open(f"{self.proc}/{pid}/cgroup") as f:
                    if "vpn-tray@" not in f.read():
                        return True
            except OSError:
                continue
        return False

    def tray_running(self) -> bool:
        r = self._run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.DBus",
                "--object-path",
                "/org/freedesktop/DBus",
                "--method",
                "org.freedesktop.DBus.NameHasOwner",
                TRAY_DBUS_NAME,
            ],
            timeout=5,
        )
        return r.ok and "true" in r.out


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
