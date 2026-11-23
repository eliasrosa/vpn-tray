"""Helper root (numa pasta temporária), unit, polkit e scripts."""
import io
import json
import os
import shutil
import stat
import subprocess

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


def test_add_saml(helper, monkeypatch, tmp_path):
    assert add(helper, monkeypatch, name="nova", host="vpn.example.net", port=10443, auth="saml")
    conf = (tmp_path / "nova.conf").read_text()
    args = (tmp_path / "nova.args").read_text()
    assert "host = vpn.example.net" in conf and "port = 10443" in conf
    assert "password" not in conf
    assert "EXTRA_ARGS=--saml-login" in args
    assert mode(tmp_path / "nova.conf") == 0o600
    assert mode(tmp_path / "nova.args") == 0o644


def test_add_senha_fica_so_no_conf(helper, monkeypatch, tmp_path):
    assert add(helper, monkeypatch, name="s", host="host.example", auth="password",
               username="u", password="s3nh4-xyz")
    assert "password = s3nh4-xyz" in (tmp_path / "s.conf").read_text()
    assert "s3nh4-xyz" not in (tmp_path / "s.args").read_text()
    assert "EXTRA_ARGS=\n" in (tmp_path / "s.args").read_text()


@pytest.mark.parametrize("data", [
    {"name": "../etc", "host": "host.example"},
    {"name": "x", "host": "h; rm -rf /"},
    {"name": "x", "host": "host.example", "realm": "a\npppd-plugin = /tmp/evil.so"},
    {"name": "x", "host": "host.example", "trusted_cert": "nope"},
    {"name": "x", "host": "host.example", "auth": "password"},
    {"name": "x", "host": "host.example", "auth": "outro"},
    {"name": "x", "host": "host.example", "port": 0},
])
def test_add_recusa_entradas_ruins(helper, monkeypatch, tmp_path, data):
    assert not add(helper, monkeypatch, **data)
    assert os.listdir(tmp_path) == []


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
    r = subprocess.run([os.path.join(ROOT, "system", "vpn-tray-helper"), "remove", "x"],
                       capture_output=True, text=True)
    if os.geteuid() != 0:
        assert r.returncode != 0 and "root" in r.stderr


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="sem systemd-analyze")
def test_unit_valida(tmp_path):
    dst = tmp_path / "vpn-tray@teste.service"
    tpl = open(os.path.join(ROOT, "system", "vpn-tray@.service")).read()
    assert "@OPENFORTIVPN@" in tpl, "o install.sh troca pelo caminho real"
    dst.write_text(tpl.replace("@OPENFORTIVPN@", shutil.which("true") or "/bin/true"))
    r = subprocess.run(["systemd-analyze", "verify", str(dst)], capture_output=True, text=True)
    problems = [l for l in (r.stdout + r.stderr).splitlines()
                if l.strip() and "/etc/openfortivpn/teste" not in l]
    assert problems == []


# A regra do polkit é testada nos dois modos em test_cli_mcp.py.


@pytest.mark.parametrize("script", ["install.sh", "uninstall.sh"])
def test_scripts_sintaxe(script):
    subprocess.run(["bash", "-n", os.path.join(ROOT, script)], check=True)
