"""vpnctl — controla as VPNs do VPN Tray pelo terminal (e por agentes).

  vpnctl status [--json]                 estado de cada VPN e política
  vpnctl connect [NOME] [--wait 120]     conecta (padrão se omitir) e espera subir
  vpnctl disconnect [NOME]               desconecta (a ativa se omitir)
  vpnctl logs [NOME] [-n 80] [-f]        log do serviço
  vpnctl import ARQUIVO [--name N]       converte um .conf do openfortivpn em perfil
  vpnctl policy [show]                   mostra a política de segurança
  vpnctl policy require-password on|off  pedir senha ao conectar (pede senha p/ mudar)
  vpnctl agents [show|enabled|allow-connect|allow-disconnect on|off]
  vpnctl mcp                             servidor MCP (stdio) para Claude/Kiro/etc.
  vpnctl setup-agents [--claude] [--kiro] [--dry-run] [--remove]

Escopo: só VPN. Testar banco/serviço é com a ferramenta de cada um.
Códigos de saída: 0 ok · 1 erro · 2 uso · 4 VPN não subiu.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .. import __version__
from ..adapters.process import run
from ..application.errors import AdminCancelled, VpnTrayError
from ..composition import Container, build
from ..domain.model import State

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_NOT_UP = 0, 1, 2, 4


def _print(data, as_json: bool, text: str) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if as_json else text)


def format_status(st: dict) -> str:
    lines = []
    if not st["profiles"]:
        lines.append("Nenhuma VPN cadastrada (adicione pelo ícone ou: vpnctl import ARQUIVO).")
    for name, p in st["profiles"].items():
        star = " ★" if name == st["default"] else ""
        extra = ""
        if p["waiting_browser_login"]:
            extra = "  → aguardando login no navegador"
        elif p["last_error"]:
            extra = f"  → {p['last_error']}"
        if p["untrusted_cert"]:
            extra += "  (certificado não confiável: confie pelo menu do ícone)"
        host = f" · {p['host']}" if p["host"] else ""
        lines.append(f"{State(p['state']).dot} {name}{star}: {p['label']} [{p['auth']}{host}]{extra}")
    if st["external_openfortivpn"]:
        lines.append("● openfortivpn rodando fora do VPN Tray (ex.: um alias/script próprio)")
    if st["ppp"]:
        lines.append("Interfaces: " + ", ".join(st["ppp"]))
    pol = "pede senha ao conectar" if st["policy"]["require_password_connect"] else "conecta sem pedir senha"
    ag = st["agents"]

    def yn(v):
        return "sim" if v else "não"

    lines.append(
        f"Segurança: {pol} · agentes: {'ligados' if ag['enabled'] else 'desligados'}, "
        f"conectar={yn(ag['allow_connect'])}, desconectar={yn(ag['allow_disconnect'])}"
    )
    return "\n".join(lines)


# ------------------------------------------------------------- comandos
def cmd_status(c: Container, a) -> int:
    st = c.status.get()
    _print(st, a.json, format_status(st))
    return EXIT_OK


def cmd_connect(c: Container, a) -> int:
    if c.policy.load().require_password_connect and not a.json:
        print("A política pede senha: confirme na caixinha que vai abrir…", file=sys.stderr)

    def on_url(url: str) -> None:
        if a.no_browser:
            print(f"Faça o login em: {url}", file=sys.stderr)
        elif not a.json:
            print("Login SAML: termine no navegador…", file=sys.stderr)

    res = c.connection.connect(a.name, wait=a.wait, open_browser=not a.no_browser, on_login_url=on_url)
    ok = res.get("state") == State.ON.value or res.get("started")
    text = (
        f"{res['profile']} já está conectada."
        if res.get("already")
        else f"{res['profile']}: iniciando…"
        if res.get("started")
        else f"{res['profile']}: {res.get('label', '?')}"
        + (f" — {res['last_error']}" if res.get("last_error") else "")
    )
    _print({"ok": bool(ok), **res}, a.json, text)
    return EXIT_OK if ok else EXIT_NOT_UP


def cmd_disconnect(c: Container, a) -> int:
    name = c.connection.disconnect(a.name)
    _print({"profile": name, "ok": True}, a.json, f"{name}: desconectada.")
    return EXIT_OK


def cmd_logs(c: Container, a) -> int:
    name = c.connection.resolve(a.name)
    if a.follow:
        os.execvp(  # noqa: S606 — substitui o processo pelo journalctl -f
            "journalctl",
            [
                "journalctl",
                "-u",
                f"vpn-tray@{name}.service",
                "-n",
                str(a.n),
                "-f",
            ],
        )
    print(c.journal.tail(name, a.n))
    return EXIT_OK


def _read_maybe_root(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except PermissionError:
        r = run(["pkexec", "cat", path], timeout=120)
        if not r.ok:
            raise VpnTrayError(f"Sem permissão para ler {path}: {r.err}") from None
        return r.out


def cmd_import(c: Container, a) -> int:
    profile, ignored = c.profiles.parse_import(_read_maybe_root(a.file), a.file, a.name)
    err = c.profiles.validate(profile)
    if err:
        raise VpnTrayError(f"Não dá para importar: {err} (use --name para escolher outro nome)")
    shown = {**profile.to_dict(), "password": "•••" if profile.password else ""}
    print("Importando:", json.dumps(shown, ensure_ascii=False))
    if ignored:
        print("Ignorando chaves não suportadas:", ", ".join(ignored))
    if a.dry_run:
        return EXIT_OK
    c.profiles.add(profile, make_default=a.default)
    print(f"perfil {profile.name} gravado")
    return EXIT_OK


def cmd_policy(c: Container, a) -> int:
    if a.action in (None, "show"):
        p = c.policy.load()
        _print(
            {"require_password_connect": p.require_password_connect},
            a.json,
            "Pedir senha ao conectar: " + ("SIM" if p.require_password_connect else "não"),
        )
        return EXIT_OK
    if a.action == "require-password" and a.value in ("on", "off"):
        c.preferences.set_require_password(a.value == "on")
        print("conectar agora pede senha" if a.value == "on" else "conectar não pede senha")
        return EXIT_OK
    print("uso: vpnctl policy [show] | vpnctl policy require-password on|off", file=sys.stderr)
    return EXIT_USAGE


def cmd_agents(c: Container, a) -> int:
    keys = {"enabled": "enabled", "allow-connect": "allow_connect", "allow-disconnect": "allow_disconnect"}
    if a.action in (None, "show"):
        ag = c.preferences.load().agents.to_dict()
        _print(ag, a.json, "\n".join(f"{k}: {'on' if v else 'off'}" for k, v in ag.items()))
        return EXIT_OK
    if a.action in keys and a.value in ("on", "off"):
        c.preferences.set_agent_permission(keys[a.action], a.value == "on")
        print(f"{keys[a.action]} = {a.value}")
        return EXIT_OK
    print("uso: vpnctl agents [show] | enabled|allow-connect|allow-disconnect on|off", file=sys.stderr)
    return EXIT_USAGE


def cmd_mcp(c: Container, _a) -> int:
    from .mcp import serve

    serve(c)
    return EXIT_OK


def cmd_setup_agents(_c: Container, a) -> int:
    from ..adapters import agent_config

    return agent_config.main(claude=a.claude, kiro=a.kiro, dry_run=a.dry_run, remove=a.remove)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="vpnctl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--version", action="version", version=f"vpnctl {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--json", action="store_true", help="saída em JSON")
        p.set_defaults(fn=fn)
        return p

    add("status", cmd_status, help="estado das VPNs")
    p = add("connect", cmd_connect, help="conecta")
    p.add_argument("name", nargs="?")
    p.add_argument("--wait", type=int, default=120, help="segundos esperando subir (0 = não espera)")
    p.add_argument("--no-browser", action="store_true", help="só imprime a URL do login")
    p = add("disconnect", cmd_disconnect, help="desconecta")
    p.add_argument("name", nargs="?")
    p = add("logs", cmd_logs, help="log do serviço")
    p.add_argument("name", nargs="?")
    p.add_argument("-n", type=int, default=80)
    p.add_argument("-f", "--follow", action="store_true")
    p = add("import", cmd_import, help="importa .conf do openfortivpn")
    p.add_argument("file")
    p.add_argument("--name")
    p.add_argument("--default", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = add("policy", cmd_policy, help="política de segurança")
    p.add_argument("action", nargs="?")
    p.add_argument("value", nargs="?")
    p = add("agents", cmd_agents, help="o que agentes podem fazer")
    p.add_argument("action", nargs="?")
    p.add_argument("value", nargs="?")
    add("mcp", cmd_mcp, help="servidor MCP (stdio)")
    p = add("setup-agents", cmd_setup_agents, help="registra MCP + skill no Claude/Kiro")
    for flag in ("--claude", "--kiro", "--dry-run", "--remove"):
        p.add_argument(flag, action="store_true")
    return ap


def main(argv: list[str] | None = None, container: Container | None = None) -> int:
    a = parser().parse_args(argv)
    if not getattr(a, "fn", None):
        parser().print_help()
        return EXIT_USAGE
    try:
        return a.fn(container or build(), a)
    except AdminCancelled as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    except VpnTrayError as e:
        if getattr(a, "json", False):
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
