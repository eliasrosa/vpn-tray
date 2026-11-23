"""Servidor MCP: protocolo, regras dos agentes e um processo de verdade."""

import io
import json
import os
import subprocess
import sys

import pytest
from conftest import ROOT

from vpntray.entrypoints.mcp import Tools, handle, serve

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}


def call(i, name, args=None):
    return {
        "jsonrpc": "2.0",
        "id": i,
        "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    }


def text(resp):
    return resp["result"]["content"][0]["text"]


@pytest.fixture
def tools(container):
    return Tools(container)


def test_handshake_e_lista(tools):
    init = handle(INIT, tools)["result"]
    assert init["serverInfo"]["name"] == "vpn-tray" and init["protocolVersion"] == "2025-06-18"
    assert "PERGUNTE" in init["instructions"]
    names = [
        t["name"]
        for t in handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, tools)["result"]["tools"]
    ]
    assert names == ["vpn_status", "vpn_connect", "vpn_disconnect", "vpn_logs"]
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, tools) is None


def test_connect_exige_confirmacao(tools):
    r = handle(call(2, "vpn_connect", {"user_confirmed": False}), tools)
    assert r["result"]["isError"] and "Pergunte ao usuário" in text(r)


def test_connect_confirmado_conecta(tools, system):
    r = handle(call(2, "vpn_connect", {"user_confirmed": True}), tools)
    data = json.loads(text(r))
    assert data["state"] == "on" and data["message"] == "Conectada."
    assert data["browser_login"] is True and system.opened


def test_connect_senha_recusada(tools, system):
    system.deny_auth = True
    r = handle(call(2, "vpn_connect", {"user_confirmed": True}), tools)
    assert r["result"]["isError"] and "não confirmou a senha" in text(r)


def test_permissoes(tools, container):
    container.preferences.set_agent_permission("allow_connect", False)
    r = handle(call(2, "vpn_connect", {"user_confirmed": True}), tools)
    assert "não permite que agentes conectem" in text(r)
    container.preferences.set_agent_permission("enabled", False)
    assert not handle(call(3, "vpn_status"), tools)["result"]["isError"]
    assert "desligados" in text(handle(call(4, "vpn_logs"), tools))


def test_disconnect_e_logs(tools, system):
    handle(call(2, "vpn_connect", {"user_confirmed": True}), tools)
    log = json.loads(text(handle(call(3, "vpn_logs", {"lines": 2}), tools)))["log"]
    assert log.endswith("Tunnel is up and running.")
    r = json.loads(text(handle(call(4, "vpn_disconnect", {"user_confirmed": True}), tools)))
    assert r == {"profile": "work", "state": "off", "message": "Desconectada."}


def test_erros_de_protocolo(tools):
    assert handle({"jsonrpc": "2.0", "id": 2, "method": "nao/existe"}, tools)["error"]["code"] == -32601
    assert handle(call(3, "ferramenta_x"), tools)["error"]["code"] == -32602
    assert handle(call(4, "__init__"), tools)["error"]["code"] == -32602, "não expõe métodos internos"


def test_serve_json_invalido_nao_derruba(container):
    out = io.StringIO()
    serve(
        container,
        io.StringIO("isso não é json\n" + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n"),
        out,
    )
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_processo_de_verdade(tmp_path):
    (tmp_path / "etc").mkdir()
    env = dict(
        os.environ,
        VPN_TRAY_CONF_DIR=str(tmp_path / "etc"),
        VPN_TRAY_SETTINGS=str(tmp_path / "s.json"),
        VPN_TRAY_POLICY=str(tmp_path / "p.json"),
    )
    payload = "\n".join(json.dumps(m) for m in [INIT, call(2, "vpn_status")]) + "\n"
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "bin", "vpnctl"), "mcp"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    replies = [json.loads(x) for x in r.stdout.splitlines()]
    assert json.loads(replies[1]["result"]["content"][0]["text"])["profiles"] == {}
