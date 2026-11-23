"""Servidor MCP (stdio, JSON-RPC 2.0) — sem dependências.

Ferramentas: vpn_status, vpn_connect, vpn_disconnect, vpn_logs.
Regras (application/agent_guard.py):
  * agents.enabled=false → só vpn_status responde;
  * conectar/desconectar exigem allow_* e user_confirmed=true;
  * com a política "pedir senha", o polkit abre a caixinha na tela do usuário.
Escopo: só VPN. Acesso a banco/serviço é com as ferramentas próprias.
"""

from __future__ import annotations

import json
import sys

from .. import __version__
from ..application.errors import AuthenticationDenied, VpnTrayError
from ..composition import Container, build
from ..domain.model import State

PROTOCOL_FALLBACK = "2025-06-18"

INSTRUCTIONS = (
    "Controle das VPNs (openfortivpn) do usuário — só VPN; acesso a banco/serviço é "
    "com as ferramentas próprias deles. Fluxo: 1) vpn_status; 2) se a VPN necessária "
    "estiver desligada, PERGUNTE ao usuário se pode conectar; 3) só com o 'sim' dele "
    "chame vpn_connect com user_confirmed=true; 4) se usar SAML, avise que o login abre "
    "no navegador; 5) vpn_status de novo e siga com a tarefa. Nunca conecte/desconecte "
    "sem confirmação."
)

TOOLS = [
    {
        "name": "vpn_status",
        "description": "Estado das VPNs (conectada/desconectada/aguardando login/erro), VPN "
        "padrão, política de senha e permissões de agentes.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "vpn_connect",
        "description": "Conecta uma VPN (a padrão se 'profile' for omitido) e espera subir. "
        "PERGUNTE ao usuário antes e só chame com user_confirmed=true depois do "
        "'sim' dele. Com SAML, o login abre no navegador do usuário; pode aparecer "
        "também uma caixinha de senha se a política exigir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "user_confirmed": {
                    "type": "boolean",
                    "description": "true só depois do usuário dizer que pode.",
                },
                "wait_seconds": {"type": "integer", "description": "Padrão 90."},
            },
            "required": ["user_confirmed"],
        },
        "annotations": {"destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "vpn_disconnect",
        "description": "Desconecta a VPN ativa (ou 'profile'). Pergunte antes; exige user_confirmed=true.",
        "inputSchema": {
            "type": "object",
            "properties": {"profile": {"type": "string"}, "user_confirmed": {"type": "boolean"}},
            "required": ["user_confirmed"],
        },
        "annotations": {"destructiveHint": True},
    },
    {
        "name": "vpn_logs",
        "description": "Últimas linhas do log da VPN (para diagnosticar falha de conexão).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "lines": {"type": "integer", "description": "Padrão 60, máx. 400."},
            },
        },
        "annotations": {"readOnlyHint": True},
    },
]


class Tools:
    def __init__(self, c: Container):
        self.c = c

    def vpn_status(self, _args: dict) -> dict:
        return self.c.status.get()

    def vpn_connect(self, args: dict) -> dict:
        self.c.guard.check("connect", args.get("user_confirmed"))
        wait = max(5, min(int(args.get("wait_seconds") or 90), 300))
        login: dict = {}
        tray = self.c.probe.tray_running()
        try:
            res = self.c.connection.connect(
                args.get("profile"), wait=wait, on_login_url=lambda u: login.setdefault("url", u)
            )
        except AuthenticationDenied:
            raise VpnTrayError(
                "O usuário não confirmou a senha (política 'pedir senha ao conectar')."
            ) from None
        if res.get("already"):
            return {"profile": res["profile"], "state": State.ON.value, "message": "Já estava conectada."}
        msg = {
            State.ON.value: "Conectada.",
            State.CONNECTING.value: "Ainda conectando — provavelmente aguardando o login no "
            "navegador; avise o usuário e consulte vpn_status em seguida.",
            State.ERROR.value: f"Falhou: {res.get('last_error') or 'veja vpn_logs'}",
            State.OFF.value: "O serviço parou logo após iniciar; veja vpn_logs.",
        }.get(res.get("state"), "?")
        return {
            "profile": res["profile"],
            "state": res.get("state"),
            "message": msg,
            "browser_login": bool(login),
            "login_opened_by": "ícone" if tray else "vpnctl",
        }

    def vpn_disconnect(self, args: dict) -> dict:
        self.c.guard.check("disconnect", args.get("user_confirmed"))
        name = self.c.connection.disconnect(args.get("profile"))
        return {"profile": name, "state": State.OFF.value, "message": "Desconectada."}

    def vpn_logs(self, args: dict) -> dict:
        self.c.guard.require_enabled()
        name = self.c.connection.resolve(args.get("profile"))
        n = max(1, min(int(args.get("lines") or 60), 400))
        return {"profile": name, "log": self.c.journal.tail(name, n)}


def handle(msg: dict, tools: Tools) -> dict | None:
    """Uma mensagem JSON-RPC -> resposta (None para notificações)."""
    mid, method = msg.get("id"), msg.get("method")
    params = msg.get("params") or {}
    if mid is None:
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok(
            {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_FALLBACK,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "vpn-tray", "version": __version__},
                "instructions": INSTRUCTIONS,
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = getattr(tools, name, None) if name in {t["name"] for t in TOOLS} else None
        if fn is None:
            return err(-32602, f"ferramenta desconhecida: {name}")
        try:
            text, is_error = (
                json.dumps(fn(params.get("arguments") or {}), ensure_ascii=False, indent=1),
                False,
            )
        except VpnTrayError as e:
            text, is_error = str(e), True
        except Exception as e:  # noqa: BLE001 — nunca derrubar o servidor
            text, is_error = f"erro interno: {type(e).__name__}: {e}", True
        return ok({"content": [{"type": "text", "text": text}], "isError": is_error})
    return err(-32601, f"método não suportado: {method}")


def serve(container: Container | None = None, stdin=None, stdout=None) -> None:
    tools = Tools(container or build())
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido"}}
        else:
            batch = msg if isinstance(msg, list) else [msg]
            replies = [r for r in (handle(m, tools) for m in batch) if r is not None]
            resp = replies if isinstance(msg, list) else (replies[0] if replies else None)
        if resp:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()
