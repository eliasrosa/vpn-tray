"""Apresentação do ícone: tooltip e menu como DADOS (testável sem GTK)."""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.model import SessionInfo, State
from ...domain.rules import first_with


def tooltip_for(
    overall: State,
    states: Mapping[str, State],
    default: str | None,
    waiting_login: bool = False,
    external: bool = False,
) -> str:
    if overall == State.ON:
        return f"VPN conectada ({first_with(states, State.ON) or 'fora do app'})"
    if overall == State.CONNECTING:
        n = first_with(states, State.CONNECTING)
        return f"VPN {n}: " + ("aguardando login no navegador" if waiting_login else "conectando…")
    if overall == State.ERROR:
        return "VPN: erro na última conexão — clique para ver"
    if default:
        return f"VPN desconectada — clique para conectar ({default})"
    return "VPN: nenhuma cadastrada — clique para adicionar"


def menu_spec(
    profiles: list[str],
    states: Mapping[str, State],
    default: str | None,
    info: Mapping[str, SessionInfo],
    external: bool = False,
    autoconnect: bool = False,
    security: Mapping | None = None,
) -> list[tuple]:
    """Menu como lista de entradas:

    ("label", texto) · ("item", texto, (ação, *args)) · ("sep",)
    ("check", texto, ativo, (ação, *args)) · ("submenu", texto, [entradas])
    ("radio", texto, [(nome, ativo, (ação, nome)), ...])
    """
    spec: list[tuple] = []
    if not profiles:
        spec.append(("label", "Nenhuma VPN cadastrada"))
    for name in profiles:
        st = states.get(name, State.OFF)
        i = info.get(name) or SessionInfo()
        star = " ★" if name == default else ""
        spec.append(("label", f"{st.dot}  {name}{star} — {st.label}"))
        if st == State.ON:
            spec.append(("item", f"Desconectar {name}", ("disconnect", name)))
        elif st == State.CONNECTING:
            if i.auth_url and not i.tunnel_up:
                spec.append(("item", "Abrir login no navegador", ("open_url", i.auth_url)))
            spec.append(("item", f"Cancelar conexão {name}", ("disconnect", name)))
        else:
            spec.append(("item", f"Conectar {name}", ("connect", name)))
        if i.untrusted_cert:
            spec.append(
                ("item", "Confiar no certificado e reconectar…", ("trust_cert", name, i.untrusted_cert))
            )
        if st == State.ERROR and i.last_error:
            spec.append(("label", f"Erro: {i.last_error[:70]}"))
        spec.append(("sep",))
    if external:
        spec.append(("label", "openfortivpn rodando fora do app"))
        spec.append(("sep",))

    spec.append(("item", "Adicionar VPN…", ("add",)))
    if profiles:
        spec.append(("submenu", "Ver log", [("item", n, ("log", n)) for n in profiles]))
    if len(profiles) > 1:
        spec.append(("radio", "VPN padrão", [(n, n == default, ("set_default", n)) for n in profiles]))
    spec.append(
        ("check", "Conectar a padrão ao iniciar a sessão", bool(autoconnect), ("toggle_autoconnect",))
    )
    sec = security or {}
    spec.append(
        (
            "submenu",
            "Segurança",
            [
                (
                    "check",
                    "Pedir senha ao conectar (vale para app, CLI e agentes)",
                    bool(sec.get("require_password")),
                    ("toggle_require_password",),
                ),
                (
                    "check",
                    "Agentes (MCP) podem conectar",
                    bool(sec.get("agents_connect")),
                    ("toggle_agents", "allow_connect"),
                ),
                (
                    "check",
                    "Agentes (MCP) podem desconectar",
                    bool(sec.get("agents_disconnect")),
                    ("toggle_agents", "allow_disconnect"),
                ),
            ],
        )
    )
    if profiles:
        spec.append(("submenu", "Remover VPN", [("item", n, ("remove", n)) for n in profiles]))
    spec.append(("sep",))
    spec.append(("item", "Sair do app (a VPN continua como está)", ("quit",)))
    return spec
