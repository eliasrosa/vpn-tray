"""Servidor MCP (stdio, JSON-RPC 2.0) do VPN Tray — sem dependências.

Registrado como `vpnctl mcp`. Ferramentas:
  vpn_status      estado das VPNs e política
  vpn_connect     conecta (exige user_confirmed=true; respeita as permissões)
  vpn_disconnect  desconecta (idem)
  vpn_logs        últimas linhas do log da VPN

Regras (ver ~/.config/vpn-tray/settings.json → "agents"):
  * agents.enabled=false   → só vpn_status responde;
  * escopo: só VPN. Testar banco/serviço é com o MCP de cada um (ex.: um MCP de banco).
  * allow_connect=false     → vpn_connect recusa;
  * allow_disconnect=false  → vpn_disconnect recusa;
  * conectar/desconectar SEMPRE exigem user_confirmed=true — o agente tem que
    perguntar ao usuário antes;
  * se a política "pedir senha ao conectar" estiver ligada, o polkit abre a
    caixinha de senha na tela do usuário — o agente não tem como pular.
"""
import json
import sys

import vpnlib as v

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
        "description": "Estado das VPNs (conectada/desconectada/aguardando login/erro), "
                       "VPN padrão, política de senha e permissões de agentes.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "vpn_connect",
        "description": "Conecta uma VPN (a padrão se 'profile' for omitido) e espera subir. "
                       "PERGUNTE ao usuário antes e só chame com user_confirmed=true depois "
                       "do 'sim' dele. Com SAML, o login abre no navegador do usuário; pode "
                       "aparecer também uma caixinha de senha se a política exigir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "user_confirmed": {"type": "boolean",
                                   "description": "true só depois do usuário dizer que pode."},
                "wait_seconds": {"type": "integer", "description": "Padrão 90."},
            },
            "required": ["user_confirmed"],
        },
        "annotations": {"destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "vpn_disconnect",
        "description": "Desconecta a VPN ativa (ou 'profile'). Pergunte antes; exige "
                       "user_confirmed=true.",
        "inputSchema": {
            "type": "object",
            "properties": {"profile": {"type": "string"},
                           "user_confirmed": {"type": "boolean"}},
            "required": ["user_confirmed"],
        },
        "annotations": {"destructiveHint": True},
    },
    {
        "name": "vpn_logs",
        "description": "Últimas linhas do log da VPN (para diagnosticar falha de conexão).",
        "inputSchema": {
            "type": "object",
            "properties": {"profile": {"type": "string"},
                           "lines": {"type": "integer", "description": "Padrão 60, máx. 400."}},
        },
        "annotations": {"readOnlyHint": True},
    },
]


class ToolError(Exception):
    pass


def _agents():
    return v.load_settings().get("agents", {})


def _require_enabled():
    if not _agents().get("enabled", True):
        raise ToolError("Agentes estão desligados no VPN Tray (vpnctl agents enabled on).")


def _pick(profile, st, active=False):
    if profile:
        if profile not in st["profiles"]:
            raise ToolError(f"VPN '{profile}' não existe. Cadastradas: "
                            f"{', '.join(st['profiles']) or 'nenhuma'}")
        return profile
    if active:
        for n, p in st["profiles"].items():
            if p["state"] in (v.ON, v.CONNECTING):
                return n
        raise ToolError("Nenhuma VPN ativa.")
    if not st["default"]:
        raise ToolError("Nenhuma VPN cadastrada.")
    return st["default"]


def tool_vpn_status(_args):
    return v.status()


def tool_vpn_connect(args):
    _require_enabled()
    if not _agents().get("allow_connect", True):
        raise ToolError("O usuário não permite que agentes conectem a VPN "
                        "(vpnctl agents allow-connect on).")
    if args.get("user_confirmed") is not True:
        raise ToolError("Pergunte ao usuário se pode conectar e chame de novo com "
                        "user_confirmed=true.")
    st = v.status()
    name = _pick(args.get("profile"), st)
    if st["profiles"][name]["state"] == v.ON:
        return {"profile": name, "state": v.ON, "message": "Já estava conectada."}
    for other, p in st["profiles"].items():
        if other != name and p["state"] in (v.ON, v.CONNECTING):
            v.systemctl("stop", other)
    code, _o, err = v.systemctl("start", name, timeout=180)
    if code != 0:
        if "authentic" in err.lower() or "autentica" in err.lower():
            raise ToolError("O usuário não confirmou a senha (política 'pedir senha ao "
                            "conectar').")
        raise ToolError(f"Falha ao iniciar: {err or code}")
    tray = v.tray_running()
    login = {}

    def on_url(url):
        login["url"] = url
        if not tray:
            v.open_browser(url)

    wait = max(5, min(int(args.get("wait_seconds") or 90), 300))
    final = v.wait_for(name, timeout=wait, on_login_url=on_url)
    msg = {v.ON: "Conectada.",
           v.CONNECTING: "Ainda conectando — provavelmente aguardando o login no navegador; "
                         "avise o usuário e consulte vpn_status em seguida.",
           v.ERROR: f"Falhou: {final.get('last_error') or 'veja vpn_logs'}",
           v.OFF: "O serviço parou logo após iniciar; veja vpn_logs."}.get(final.get("state"), "?")
    return {"profile": name, "state": final.get("state"), "message": msg,
            "browser_login": bool(login), "login_opened_by": "ícone" if tray else "vpnctl"}


def tool_vpn_disconnect(args):
    _require_enabled()
    if not _agents().get("allow_disconnect", True):
        raise ToolError("O usuário não permite que agentes desconectem a VPN.")
    if args.get("user_confirmed") is not True:
        raise ToolError("Pergunte ao usuário e chame de novo com user_confirmed=true.")
    st = v.status()
    name = _pick(args.get("profile"), st, active=True)
    code, _o, err = v.systemctl("stop", name)
    if code != 0:
        raise ToolError(err or "falhou")
    return {"profile": name, "state": v.OFF, "message": "Desconectada."}


def tool_vpn_logs(args):
    _require_enabled()
    st = v.status()
    name = _pick(args.get("profile"), st)
    n = max(1, min(int(args.get("lines") or 60), 400))
    return {"profile": name, "log": v.logs(name, n)}


HANDLERS = {
    "vpn_status": tool_vpn_status,
    "vpn_connect": tool_vpn_connect,
    "vpn_disconnect": tool_vpn_disconnect,
    "vpn_logs": tool_vpn_logs,
}


def handle(msg):
    """Uma mensagem JSON-RPC -> resposta (ou None para notificações)."""
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    if mid is None:  # notificação
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_FALLBACK,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "vpn-tray", "version": v.__version__},
            "instructions": INSTRUCTIONS,
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if not fn:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": f"ferramenta desconhecida: {name}"}}
        try:
            data = fn(params.get("arguments") or {})
            text, is_error = json.dumps(data, ensure_ascii=False, indent=1), False
        except ToolError as e:
            text, is_error = str(e), True
        except Exception as e:  # noqa: BLE001 — nunca derrubar o servidor
            text, is_error = f"erro interno: {type(e).__name__}: {e}", True
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": text}], "isError": is_error}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"método não suportado: {method}"}}


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "JSON inválido"}}
        else:
            batch = msg if isinstance(msg, list) else [msg]
            replies = [r for r in (handle(m) for m in batch) if r is not None]
            resp = replies if isinstance(msg, list) else (replies[0] if replies else None)
        if resp:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()
