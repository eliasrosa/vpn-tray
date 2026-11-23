"""Adaptador do helper root (via pkexec). O helper em si fica em system/."""

from __future__ import annotations

import json
import os
from collections.abc import Callable

from ..application.errors import AdminCancelled, AdminError
from ..domain.model import NewProfile
from .process import run

DEFAULT_HELPER = "/usr/local/libexec/vpn-tray/vpn-tray-helper"


class PkexecProfileAdmin:
    def __init__(self, helper: str = DEFAULT_HELPER, runner: Callable = run):
        self.helper = helper
        self._run = runner

    def _call(self, args: list[str], stdin: str | None = None) -> str:
        if not os.path.exists(self.helper):
            raise AdminError("VPN Tray não está instalado: rode o install.sh.")
        r = self._run(["pkexec", self.helper, *args], timeout=300, input_text=stdin)
        if r.code in (126, 127):  # senha cancelada / não autorizado no pkexec
            raise AdminCancelled("Senha cancelada.")
        if not r.ok:
            raise AdminError(r.err or "falhou")
        return r.out.strip()

    def add(self, profile: NewProfile) -> None:
        self._call(["add"], json.dumps(profile.to_dict()))

    def remove(self, name: str) -> None:
        self._call(["remove", name])

    def trust(self, name: str, digest: str) -> None:
        self._call(["trust", name, digest])

    def set_require_password(self, enabled: bool) -> None:
        self._call(["policy", "require-password", "on" if enabled else "off"])
