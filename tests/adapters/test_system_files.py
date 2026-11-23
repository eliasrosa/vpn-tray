"""Partes que rodam como root ou no sistema: helper, unit, polkit e scripts."""

import io
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import ROOT, load_helper


@pytest.fixture
def helper(tmp_path):
    h = load_helper()
    h.CONF_DIR = str(tmp_path)
    return h


def add(h, monkeypatch, **data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    try:
        h.cmd_add()
        return True
    except SystemExit:
        return False


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


# ------------------------------------------------------------------ helper
def test_add_saml(helper, monkeypatch, tmp_path):
    assert add(helper, monkeypatch, name="nova", host="vpn.example.net", port=10443, auth="saml")
    conf, args = (tmp_path / "nova.conf").read_text(), (tmp_path / "nova.args").read_text()
    assert "host = vpn.example.net" in conf and "port = 10443" in conf and "password" not in conf
    assert "EXTRA_ARGS=--saml-login" in args
    assert mode(tmp_path / "nova.conf") == 0o600 and mode(tmp_path / "nova.args") == 0o644


def test_add_senha_fica_so_no_conf(helper, monkeypatch, tmp_path):
    assert add(
        helper,
        monkeypatch,
        name="s",
        host="host.example",
        auth="password",
        username="u",
        password="s3nh4-xyz",
    )
    assert "password = s3nh4-xyz" in (tmp_path / "s.conf").read_text()
    assert "s3nh4-xyz" not in (tmp_path / "s.args").read_text()


def test_trust_nao_duplica(helper, monkeypatch, tmp_path):
    add(helper, monkeypatch, name="c", host="host.example")
    helper.cmd_trust("c", "AB" * 32)
    helper.cmd_trust("c", "ab" * 32)
    assert (tmp_path / "c.conf").read_text().count("trusted-cert = " + "ab" * 32) == 1


def test_remove(helper, monkeypatch, tmp_path):
    add(helper, monkeypatch, name="c", host="host.example")
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: None)
    helper.cmd_remove("c")
    assert os.listdir(tmp_path) == []


def test_helper_exige_root():
    r = subprocess.run(
        [os.path.join(ROOT, "system", "vpn-tray-helper"), "remove", "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    if os.geteuid() != 0:
        assert r.returncode != 0 and "root" in r.stderr


def test_policy_grava_arquivos(tmp_path, monkeypatch):
    h = load_helper()
    tpl = tmp_path / "tpl"
    shutil.copy(os.path.join(ROOT, "system", "50-vpn-tray.rules.in"), tpl)
    for attr, value in {
        "POLICY_DIR": tmp_path / "pol",
        "POLICY_FILE": tmp_path / "pol" / "p.json",
        "RULE_TEMPLATE": tpl,
        "RULE_FILE": tmp_path / "rule.rules",
    }.items():
        monkeypatch.setattr(h, attr, str(value))
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
    h.cmd_policy(["require-password", "on"])
    assert json.loads((tmp_path / "pol" / "p.json").read_text())["require_password_connect"]
    assert "AUTH_SELF" in (tmp_path / "rule.rules").read_text()
    h.cmd_policy(["apply"])
    assert "AUTH_SELF" in (tmp_path / "rule.rules").read_text(), "reaplicar mantém"
    h.cmd_policy(["require-password", "off"])
    assert "AUTH_SELF" not in (tmp_path / "rule.rules").read_text()


def test_render_rule_recusa_usuario_invalido():
    h = load_helper()
    tpl = Path(ROOT, "system", "50-vpn-tray.rules.in").read_text()
    on = h.render_rule(tpl, "alice", True)
    assert "return polkit.Result.AUTH_SELF;" in on and "@USER@" not in on
    with pytest.raises(SystemExit):
        h.render_rule(tpl, 'alice"; evil', True)


# ------------------------------------------------------------------ polkit
@pytest.mark.skipif(not shutil.which("node"), reason="sem node para rodar a regra JS")
@pytest.mark.parametrize("require_password", [False, True])
def test_regra_polkit_nos_dois_modos(require_password):
    rule = load_helper().render_rule(
        Path(ROOT, "system", "50-vpn-tray.rules.in").read_text(), "alice", require_password
    )
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
      r.traversal = ask('vpn-tray@../x.service', 'start');
      r.other = ask('vpn-tray@work.service', 'start', 'bob');
      r.remote = ask('vpn-tray@work.service', 'start', 'alice', false);
    }};
    eval(RULE); console.log(JSON.stringify(r));
    """.replace("RULE", json.dumps(rule))
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert out == {
        "start": "auth_self" if require_password else "yes",
        "stop": "yes",
        "enable": "no",
        "ssh": "no",
        "traversal": "no",
        "other": "no",
        "remote": "no",
    }


# ------------------------------------------------------------ unit / scripts
@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="sem systemd-analyze")
def test_unit_valida(tmp_path):
    tpl = Path(ROOT, "system", "vpn-tray@.service").read_text()
    assert "@OPENFORTIVPN@" in tpl, "o install.sh troca pelo caminho real"
    dst = tmp_path / "vpn-tray@teste.service"
    dst.write_text(tpl.replace("@OPENFORTIVPN@", shutil.which("true") or "/bin/true"))
    r = subprocess.run(["systemd-analyze", "verify", str(dst)], capture_output=True, text=True, check=False)
    problems = [
        ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip() and "/etc/openfortivpn/teste" not in ln
    ]
    assert problems == []


@pytest.mark.parametrize("script", ["install.sh", "uninstall.sh"])
def test_scripts_sintaxe(script):
    subprocess.run(["bash", "-n", os.path.join(ROOT, script)], check=True)
