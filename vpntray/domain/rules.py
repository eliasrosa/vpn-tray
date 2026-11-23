"""Regras de negócio puras."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .model import Auth, NewProfile, State

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

_ACTIVE = ("active", "activating")


def unit_name(profile: str) -> str:
    return f"vpn-tray@{profile}.service"


def is_running(active_state: str) -> bool:
    return active_state in ("active", "activating", "deactivating")


def profile_state(active_state: str, tunnel_up: bool) -> State:
    if active_state == "failed":
        return State.ERROR
    if active_state in _ACTIVE:
        return State.ON if tunnel_up else State.CONNECTING
    if active_state == "deactivating":
        return State.CONNECTING
    return State.OFF


def overall_state(states: Mapping[str, State], external: bool = False) -> State:
    values = set(states.values())
    for s in (State.ON, State.CONNECTING, State.ERROR):
        if s in values:
            return s
    return State.ON if external else State.OFF


def first_with(states: Mapping[str, State], wanted: State) -> str | None:
    return next((k for k, v in states.items() if v == wanted), None)


def normalize_cert(value: str) -> str:
    return (value or "").lower().replace(":", "").strip()


def validate_new_profile(p: NewProfile, existing: Mapping | set | list) -> str | None:
    """Mensagem de erro (para o usuário) ou None. Espelha o helper root."""
    if not p.name:
        return "Dê um nome para a VPN."
    if not NAME_RE.match(p.name):
        return "Nome: só letras minúsculas, números, - e _ (até 32)."
    if p.name in existing:
        return f"Já existe uma VPN chamada “{p.name}”."
    if not p.host:
        return "Informe o servidor."
    if not HOST_RE.match(p.host):
        return "Servidor inválido (ex.: vpn.example.com)."
    if not isinstance(p.port, int) or not 0 < p.port < 65536:
        return "Porta inválida."
    if p.auth not in (Auth.SAML.value, Auth.PASSWORD.value):
        return "Autenticação inválida."
    if p.auth == Auth.PASSWORD.value and not (p.username and p.password):
        return "Informe usuário e senha."
    cert = normalize_cert(p.trusted_cert)
    if cert and not HASH_RE.match(cert):
        return "Certificado: cole o SHA256 em hex (64 caracteres)."
    for key, value in p.to_dict().items():
        if isinstance(value, str) and any(c in value for c in "\r\n\0"):
            return f"Campo inválido: {key}"
    return None


def pick_profile(
    requested: str | None, profiles: Mapping, default: str | None, active: list[str] | None = None
) -> str:
    """Resolve qual perfil usar. Lança LookupError com mensagem amigável."""
    if requested:
        if requested not in profiles:
            raise LookupError(
                f"VPN “{requested}” não existe. Cadastradas: {', '.join(profiles) or 'nenhuma'}"
            )
        return requested
    if active is not None:
        if not active:
            raise LookupError("Nenhuma VPN ativa.")
        return active[0]
    if default in profiles:
        return default
    if profiles:
        return next(iter(profiles))
    raise LookupError("Nenhuma VPN cadastrada.")
