"""CLI (vpnctl), servidor MCP, import e política do polkit.

Rodam com pastas temporárias (VPN_TRAY_CONF_DIR/SETTINGS/POLICY): não tocam
na VPN de verdade nem nas suas configurações.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT, load_helper

VPNCTL = os.path.join(ROOT, "vpnctl")


@pytest.fixture
def env(tmp_path):
    conf = tmp_path / "etc"
    conf.mkdir()
    e = dict(os.environ,
             VPN_TRAY_CONF_DIR=str(conf),
             VPN_TRAY_SETTINGS=str(tmp_path / "settings.json"),
             VPN_TRAY_POLICY=str(tmp_path / "policy.json"))
    return e


def vpnctl(env, *args):
    r = subprocess.run([sys.executable, VPNCTL, *args], capture_output=True, text=True,
                       env=env, timeout=60)
    return r.returncode, r.stdout, r.stderr


# ------------------------------------------------------------------ CLI
def test_status_sem_vpns(env):
    code, out, _ = vpnctl(env, "status", "--json")
    assert code == 0
    st = json.loads(out)
    assert st["profiles"] == {} and st["overall"] == "off"
    assert st["agents"]["allow_connect"] is True


def test_status_lista_perfil(env, tmp_path):
    (tmp_path / "etc" / "zz-teste-isolado.args").write_text("EXTRA_ARGS=--saml-login\nVPN_HOST=vpn.x\n"
                                                 "VPN_AUTH=saml\n")
    code, out, _ = vpnctl(env, "status")
    assert code == 0
    assert "zz-teste-isolado ★: desconectada [saml · vpn.x]" in out


def test_import_dry_run_converte_conf(env, tmp_path):
    f = tmp_path / "Empresa.conf"
    f.write_text("host = vpn.example.com:10443\nusername = ana\npassword = s3gr3d0\n"
                 "set-routes = 1\n# comentario\n")
    code, out, _ = vpnctl(env, "import", str(f), "--dry-run")
    assert code == 0
    assert '"name": "empresa"' in out and '"port": 10443' in out
    assert '"auth": "password"' in out
    assert "s3gr3d0" not in out, "não mostra a senha"
    assert "Ignorando chaves não suportadas: set-routes" in out


def test_connect_sem_vpn_cadastrada(env):
    code, _o, err = vpnctl(env, "connect", "--wait", "0")
    assert code == 1 and "Nenhuma VPN cadastrada" in err


def test_agents_on_off(env):
    assert vpnctl(env, "agents", "allow-connect", "off")[0] == 0
    code, out, _ = vpnctl(env, "agents", "--json")
    assert json.loads(out)["allow_connect"] is False


# ------------------------------------------------------------------ MCP
def mcp_session(env, *messages):
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    r = subprocess.run([sys.executable, VPNCTL, "mcp"], input=payload, capture_output=True,
                       text=True, env=env, timeout=60)
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def call(i, name, args=None):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": name, "arguments": args or {}}}


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "pytest", "version": "0"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def test_mcp_handshake_e_lista_de_ferramentas(env):
    r = mcp_session(env, INIT, INITIALIZED, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(r) == 2, "notificação não tem resposta"
    assert r[0]["result"]["serverInfo"]["name"] == "vpn-tray"
    assert r[0]["result"]["protocolVersion"] == "2025-06-18"
    assert "PERGUNTE" in r[0]["result"]["instructions"]
    names = [t["name"] for t in r[1]["result"]["tools"]]
    assert names == ["vpn_status", "vpn_connect", "vpn_disconnect", "vpn_logs"]
    assert not any("check" in n for n in names), "escopo é só VPN"
    connect = next(t for t in r[1]["result"]["tools"] if t["name"] == "vpn_connect")
    assert connect["inputSchema"]["required"] == ["user_confirmed"]


def test_mcp_connect_exige_confirmacao(env):
    r = mcp_session(env, INIT, call(2, "vpn_connect", {"user_confirmed": False}))
    res = r[1]["result"]
    assert res["isError"] and "Pergunte ao usuário" in res["content"][0]["text"]


def test_mcp_respeita_agents_allow_connect(env):
    vpnctl(env, "agents", "allow-connect", "off")
    r = mcp_session(env, INIT, call(2, "vpn_connect", {"user_confirmed": True}))
    assert "não permite que agentes conectem" in r[1]["result"]["content"][0]["text"]


def test_mcp_agentes_desligados_so_status(env):
    vpnctl(env, "agents", "enabled", "off")
    r = mcp_session(env, INIT, call(2, "vpn_status"), call(3, "vpn_logs"))
    assert not r[1]["result"]["isError"]
    assert r[2]["result"]["isError"]
    assert "desligados" in r[2]["result"]["content"][0]["text"]


def test_mcp_erros_de_protocolo(env):
    r = mcp_session(env, INIT, {"jsonrpc": "2.0", "id": 2, "method": "nao/existe"},
                    call(3, "ferramenta_x"))
    assert r[1]["error"]["code"] == -32601
    assert r[2]["error"]["code"] == -32602


def test_mcp_json_invalido_nao_derruba(env):
    r = subprocess.run([sys.executable, VPNCTL, "mcp"], input="isso não é json\n"
                       + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n",
                       capture_output=True, text=True, env=env, timeout=30)
    lines = [json.loads(x) for x in r.stdout.splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


# -------------------------------------------------------- setup dos agentes
def test_setup_agents_dry_run_nao_mexe_em_nada(env, tmp_path):
    home = tmp_path / "home"
    (home / ".kiro" / "settings").mkdir(parents=True)
    e = dict(env, HOME=str(home), PATH="/usr/bin:/bin")
    code, out, _ = vpnctl(e, "setup-agents", "--kiro", "--dry-run")
    assert code == 0 and "Kiro: MCP 'vpn-tray'" in out
    assert not (home / ".kiro" / "settings" / "mcp.json").exists()


def test_setup_agents_kiro_preserva_outros_servidores(env, tmp_path):
    home = tmp_path / "home"
    (home / ".kiro" / "settings").mkdir(parents=True)
    mcp = home / ".kiro" / "settings" / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"grafana": {"command": "x"}}}))
    e = dict(env, HOME=str(home))
    assert vpnctl(e, "setup-agents", "--kiro")[0] == 0
    data = json.loads(mcp.read_text())
    assert set(data["mcpServers"]) == {"grafana", "vpn-tray"}
    assert data["mcpServers"]["vpn-tray"]["args"] == ["mcp"]
    assert data["mcpServers"]["vpn-tray"]["autoApprove"] == ["vpn_status", "vpn_logs"]
    skill = home / ".kiro" / "skills" / "vpn-tray" / "SKILL.md"
    assert skill.is_symlink() and "name: vpn-tray" in skill.read_text()
    assert list((home / ".kiro" / "settings").glob("mcp.json.bak-vpn-tray-*"))
    assert vpnctl(e, "setup-agents", "--kiro", "--remove")[0] == 0
    assert set(json.loads(mcp.read_text())["mcpServers"]) == {"grafana"}
    assert not skill.exists()


# ------------------------------------------------------------- política
def test_helper_render_rule_dois_modos():
    h = load_helper()
    tpl = open(os.path.join(ROOT, "system", "50-vpn-tray.rules.in")).read()
    off = h.render_rule(tpl, "alice", False)
    on = h.render_rule(tpl, "alice", True)
    assert "return polkit.Result.YES;" in off and "AUTH_SELF" not in off
    assert "return polkit.Result.AUTH_SELF;" in on
    assert "@USER@" not in on and "@CONNECT" not in on
    with pytest.raises(SystemExit):
        h.render_rule(tpl, "alice\"; evil", True)


def test_helper_policy_grava_arquivos(tmp_path, monkeypatch):
    h = load_helper()
    tpl = tmp_path / "tpl"
    shutil.copy(os.path.join(ROOT, "system", "50-vpn-tray.rules.in"), tpl)
    monkeypatch.setattr(h, "POLICY_DIR", str(tmp_path / "pol"))
    monkeypatch.setattr(h, "POLICY_FILE", str(tmp_path / "pol" / "policy.json"))
    monkeypatch.setattr(h, "RULE_TEMPLATE", str(tpl))
    monkeypatch.setattr(h, "RULE_FILE", str(tmp_path / "rule.rules"))
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
    h.cmd_policy(["require-password", "on"])
    assert json.loads((tmp_path / "pol" / "policy.json").read_text())[
        "require_password_connect"] is True
    assert "AUTH_SELF" in (tmp_path / "rule.rules").read_text()
    h.cmd_policy(["apply"])  # reaplicar mantém
    assert "AUTH_SELF" in (tmp_path / "rule.rules").read_text()
    h.cmd_policy(["require-password", "off"])
    assert "AUTH_SELF" not in (tmp_path / "rule.rules").read_text()


@pytest.mark.skipif(not shutil.which("node"), reason="sem node")
@pytest.mark.parametrize("require_password", [False, True])
def test_regra_polkit_nos_dois_modos(require_password):
    h = load_helper()
    rule = h.render_rule(open(os.path.join(ROOT, "system", "50-vpn-tray.rules.in")).read(),
                         "alice", require_password)
    js = r"""
    const r = {};
    const polkit = {Result: {YES: 'yes', AUTH_SELF: 'auth_self'}, addRule(f) {
      const ask = (unit, verb, user='alice', local=true) => f(
        {id: 'org.freedesktop.systemd1.manage-units', lookup: k => ({unit, verb})[k]},
        {user, local, active: true}) || 'no';
      r.start = ask('vpn-tray@work.service', 'start');
      r.stop = ask('vpn-tray@work.service', 'stop');
      r.enable = ask('vpn-tray@work.service', 'enable');
      r.ssh = ask('ssh.service', 'stop');
      r.other = ask('vpn-tray@work.service', 'start', 'bob');
    }};
    eval(RULE); console.log(JSON.stringify(r));
    """.replace("RULE", json.dumps(rule))
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == {"start": "auth_self" if require_password else "yes", "stop": "yes",
                   "enable": "no", "ssh": "no", "other": "no"}


# ------------------------------------------------------------ vpnlib puro
def test_parse_openfortivpn_conf():
    import vpnlib as v
    data, ignored = v.parse_openfortivpn_conf(
        "host = vpn.example.net\nport = 8443\nrealm = r1\ntrusted-cert = " + "a" * 64 + "\n"
        "trusted-cert = " + "b" * 64 + "\npppd-plugin = /x.so\n", "a")
    assert data["host"] == "vpn.example.net" and data["port"] == 8443 and data["auth"] == "saml"
    assert data["realm"] == "r1" and data["trusted_cert"] == "a" * 64
    assert ignored == ["pppd-plugin"], "pppd-plugin nunca é importado"


def test_wait_for_para_quando_sobe(monkeypatch):
    import vpnlib as v
    seq = iter([{"state": "off"}, {"state": "connecting", "login_url": "https://l"},
                {"state": "connecting", "login_url": "https://l"}, {"state": "on"}])
    monkeypatch.setattr(v, "status", lambda: {"profiles": {"c": next(seq)}})
    t = [0.0]
    urls = []
    res = v.wait_for("c", timeout=60, on_login_url=urls.append, clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + s))
    assert res["state"] == "on" and urls == ["https://l"], "URL anunciada uma vez só"
