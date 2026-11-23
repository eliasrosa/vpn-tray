"""Conhecimento sobre o openfortivpn: formato do .conf e mensagens do log."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from .model import Auth, NewProfile, SessionInfo

RE_AUTH = re.compile(r"Authenticate at '([^']+)'")
RE_CERT = re.compile(r"trusted-cert\s*=\s*([0-9a-f]{64})")
RE_UP = re.compile(r"Tunnel is up and running")
RE_ERR = re.compile(r"ERROR:\s*(.+)")

SUPPORTED_KEYS = ("host", "port", "username", "password", "realm", "trusted-cert")


def parse_args_file(text: str) -> dict[str, str]:
    """<nome>.args (KEY=VALUE, sem segredos) -> dict."""
    meta: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta


def parse_conf(text: str, name: str = "") -> tuple[NewProfile, list[str]]:
    """Config do openfortivpn -> (perfil, chaves ignoradas).

    Só as chaves de SUPPORTED_KEYS são aproveitadas; o resto (ex.: pppd-plugin)
    nunca é importado.
    """
    kv: dict[str, str] = {}
    certs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if k == "trusted-cert":
            certs.append(v)
        else:
            kv[k] = v
    host = kv.get("host", "")
    port = kv.get("port", "443")
    if ":" in host and not host.startswith("["):  # host = vpn.example.com:10443
        host, _, port = host.partition(":")
    profile = NewProfile(
        name=name,
        host=host,
        port=int(port) if str(port).isdigit() else 443,
        auth=Auth.PASSWORD.value if kv.get("password") else Auth.SAML.value,
        username=kv.get("username", ""),
        password=kv.get("password", ""),
        realm=kv.get("realm", ""),
        trusted_cert=certs[0] if certs else "",
    )
    ignored = sorted(k for k in kv if k not in SUPPORTED_KEYS)
    return profile, ignored


def summarize(lines: Iterable[str]) -> SessionInfo:
    info = SessionInfo()
    for line in lines:
        apply_line(info, line)
    return info


def apply_line(info: SessionInfo, line: str) -> list[str]:
    """Atualiza `info` com uma linha do log; devolve os eventos novos
    ("auth", "cert", "up") — cada um só uma vez por execução."""
    events = []
    m = RE_AUTH.search(line)
    if m and not info.auth_url:
        info.auth_url = m.group(1)
        events.append("auth")
    m = RE_CERT.search(line)
    if m and not info.untrusted_cert:
        info.untrusted_cert = m.group(1)
        events.append("cert")
    if RE_UP.search(line) and not info.tunnel_up:
        info.tunnel_up = True
        events.append("up")
    m = RE_ERR.search(line)
    if m:
        info.last_error = m.group(1).strip()
    return events


class LogSession:
    """Acompanha uma execução (InvocationID) linha a linha.

    live=False: execução que já existia quando começamos a observar — o log é
    relido do início, então não dispara eventos (não reabre o navegador).
    """

    def __init__(
        self, profile: str, invocation: str, live: bool, on_event: Callable[[str, LogSession], None]
    ):
        self.profile = profile
        self.invocation = invocation
        self.live = live
        self.info = SessionInfo()
        self._on_event = on_event
        self.handle = None

    def feed(self, line: str) -> None:
        for event in apply_line(self.info, line.strip()):
            if self.live:
                self._on_event(event, self)
        self._on_event("changed", self)

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None
