"""vpnctl de ponta a ponta (processo de verdade, pastas temporárias) e em memória."""

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

import pytest
from conftest import ROOT

from vpntray.entrypoints.cli import main

VPNCTL = os.path.join(ROOT, "bin", "vpnctl")


@pytest.fixture
def env(tmp_path):
    (tmp_path / "etc").mkdir()
    return dict(
        os.environ,
        VPN_TRAY_CONF_DIR=str(tmp_path / "etc"),
        VPN_TRAY_SETTINGS=str(tmp_path / "settings.json"),
        VPN_TRAY_POLICY=str(tmp_path / "policy.json"),
    )


def vpnctl(env, *args):
    r = subprocess.run(
        [sys.executable, VPNCTL, *args], capture_output=True, text=True, env=env, timeout=60, check=False
    )
    return r.returncode, r.stdout, r.stderr


def run_mem(container, *args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(args), container)
    return code, buf.getvalue()


# ------------------------------------------------------ processo de verdade
def test_version(env):
    code, out, _ = vpnctl(env, "--version")
    assert code == 0 and out.startswith("vpnctl ")


def test_status_sem_vpns(env):
    code, out, _ = vpnctl(env, "status", "--json")
    st = json.loads(out)
    assert code == 0 and st["profiles"] == {} and st["overall"] == "off"


def test_status_lista_perfil(env, tmp_path):
    (tmp_path / "etc" / "zz-teste-isolado.args").write_text(
        "EXTRA_ARGS=--saml-login\nVPN_HOST=vpn.example.net\nVPN_AUTH=saml\n"
    )
    code, out, _ = vpnctl(env, "status")
    assert code == 0 and "zz-teste-isolado ★: desconectada [saml · vpn.example.net]" in out


def test_import_dry_run(env, tmp_path):
    f = tmp_path / "Empresa.conf"
    f.write_text("host = vpn.example.com:10443\nusername = ana\npassword = s3gr3d0\nset-routes = 1\n")
    code, out, _ = vpnctl(env, "import", str(f), "--dry-run")
    assert code == 0 and '"name": "empresa"' in out and '"port": 10443' in out
    assert "s3gr3d0" not in out, "não mostra a senha"
    assert "Ignorando chaves não suportadas: set-routes" in out


def test_connect_sem_vpn_cadastrada(env):
    code, _o, err = vpnctl(env, "connect", "--wait", "0")
    assert code == 1 and "Nenhuma VPN cadastrada" in err


def test_agents_on_off(env):
    assert vpnctl(env, "agents", "allow-connect", "off")[0] == 0
    assert json.loads(vpnctl(env, "agents", "--json")[1])["allow_connect"] is False


def test_uso_invalido(env):
    assert vpnctl(env)[0] == 2
    assert vpnctl(env, "policy", "require-password", "talvez")[0] == 2


# ------------------------------------------------------------ em memória
def test_connect_e_disconnect(container, system):
    code, out = run_mem(container, "connect", "work", "--json")
    res = json.loads(out)
    assert code == 0 and res["ok"] and res["state"] == "on"
    code, out = run_mem(container, "disconnect")
    assert code == 0 and "work: desconectada." in out


def test_connect_que_nao_sobe_sai_com_4(container):
    code, out = run_mem(container, "connect", "quebrada", "--json")
    assert code == 4 and json.loads(out)["state"] == "error"


def test_policy_pelo_cli(container, system):
    assert run_mem(container, "policy", "require-password", "on")[0] == 0
    assert system.policy_data.require_password_connect
    assert "SIM" in run_mem(container, "policy")[1]
