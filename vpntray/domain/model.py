"""Entidades e objetos de valor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    OFF = "off"
    CONNECTING = "connecting"
    ON = "on"
    ERROR = "error"

    @property
    def label(self) -> str:
        return {
            State.OFF: "desconectada",
            State.CONNECTING: "conectando…",
            State.ON: "conectada",
            State.ERROR: "erro",
        }[self]

    @property
    def dot(self) -> str:
        return {State.OFF: "○", State.CONNECTING: "◐", State.ON: "●", State.ERROR: "✕"}[self]


class Auth(str, Enum):
    SAML = "saml"
    PASSWORD = "password"  # noqa: S105 — nome do modo de login, não é senha


@dataclass(frozen=True)
class ProfileMeta:
    """O que se sabe de um perfil sem ler segredos (vem do <nome>.args)."""

    name: str
    auth: str = "?"
    host: str = ""


@dataclass(frozen=True)
class UnitInfo:
    """Estado da unit do systemd de um perfil."""

    active_state: str = "inactive"
    invocation_id: str = ""


@dataclass
class SessionInfo:
    """O que o log de uma execução diz (login SAML, túnel, certificado, erro)."""

    auth_url: str | None = None
    tunnel_up: bool = False
    untrusted_cert: str | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class Policy:
    require_password_connect: bool = False


@dataclass
class AgentPermissions:
    enabled: bool = True
    allow_connect: bool = True
    allow_disconnect: bool = True

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "allow_connect": self.allow_connect,
            "allow_disconnect": self.allow_disconnect,
        }


@dataclass
class Settings:
    default: str | None = None
    autoconnect: bool = False
    agents: AgentPermissions = field(default_factory=AgentPermissions)
    extra: dict = field(default_factory=dict)  # chaves desconhecidas são preservadas

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        data = dict(data or {})
        agents = AgentPermissions(
            **{
                k: bool(v)
                for k, v in (data.pop("agents", {}) or {}).items()
                if k in ("enabled", "allow_connect", "allow_disconnect")
            }
        )
        return cls(
            default=data.pop("default", None),
            autoconnect=bool(data.pop("autoconnect", False)),
            agents=agents,
            extra=data,
        )

    def to_dict(self) -> dict:
        return {
            **self.extra,
            "default": self.default,
            "autoconnect": self.autoconnect,
            "agents": self.agents.to_dict(),
        }


@dataclass(frozen=True)
class NewProfile:
    """Dados de um perfil novo (formulário, import de .conf)."""

    name: str
    host: str
    port: int = 443
    auth: str = Auth.SAML.value
    username: str = ""
    password: str = ""
    realm: str = ""
    trusted_cert: str = ""

    def public_dict(self) -> dict:
        """Para mostrar ao usuário/logar: NUNCA inclui a senha, só se ela existe."""
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "auth": self.auth,
            "username": self.username,
            "password_set": bool(self.password),
            "realm": self.realm,
            "trusted_cert": self.trusted_cert,
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "auth": self.auth,
            "username": self.username,
            "password": self.password,
            "realm": self.realm,
            "trusted_cert": self.trusted_cert,
        }
