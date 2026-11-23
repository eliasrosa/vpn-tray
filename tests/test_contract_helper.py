"""Contrato: o helper root e o domínio recusam as MESMAS entradas.

O helper é autocontido de propósito (roda como root e não pode importar
código de uma pasta que o usuário edita), então a validação existe em dois
lugares. Este teste garante que eles não divergem.
"""

import io
import json

import pytest
from conftest import load_helper

from vpntray.domain.model import NewProfile
from vpntray.domain.rules import validate_new_profile

CASES = [
    ({"name": "ok", "host": "vpn.example.com"}, True),
    (
        {
            "name": "ok",
            "host": "vpn.example.com",
            "port": 10443,
            "auth": "password",
            "username": "alice",
            "password": "s3nh4",
        },
        True,
    ),
    ({"name": "ok", "host": "vpn.example.com", "trusted_cert": "ab" * 32}, True),
    ({"name": "../etc", "host": "vpn.example.com"}, False),
    ({"name": "Maiuscula", "host": "vpn.example.com"}, False),
    ({"name": "x" * 33, "host": "vpn.example.com"}, False),
    ({"name": "ok", "host": "h; rm -rf /"}, False),
    ({"name": "ok", "host": ""}, False),
    ({"name": "ok", "host": "vpn.example.com", "port": 0}, False),
    ({"name": "ok", "host": "vpn.example.com", "port": 70000}, False),
    ({"name": "ok", "host": "vpn.example.com", "auth": "outro"}, False),
    ({"name": "ok", "host": "vpn.example.com", "auth": "password"}, False),
    ({"name": "ok", "host": "vpn.example.com", "trusted_cert": "nope"}, False),
    ({"name": "ok", "host": "vpn.example.com", "realm": "a\npppd-plugin = /tmp/evil.so"}, False),
]


@pytest.mark.parametrize("data,accepted", CASES, ids=[json.dumps(c[0])[:60] for c in CASES])
def test_helper_e_dominio_concordam(tmp_path, monkeypatch, data, accepted):
    domain_ok = validate_new_profile(NewProfile(**data), {}) is None
    h = load_helper()
    h.CONF_DIR = str(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    try:
        h.cmd_add()
        helper_ok = True
    except SystemExit:
        helper_ok = False
    assert domain_ok == accepted, "domínio"
    assert helper_ok == accepted, "helper root"
