"""Domínio: regras puras, sem I/O."""

import pytest

from vpntray.domain.model import AgentPermissions, NewProfile, Settings, State
from vpntray.domain.openfortivpn import LogSession, parse_args_file, parse_conf, summarize
from vpntray.domain.rules import overall_state, pick_profile, profile_state, validate_new_profile


# ------------------------------------------------------------------ estados
def test_profile_state():
    assert profile_state("inactive", False) == State.OFF
    assert profile_state("activating", False) == State.CONNECTING
    assert profile_state("active", False) == State.CONNECTING  # aguardando SAML
    assert profile_state("active", True) == State.ON
    assert profile_state("deactivating", True) == State.CONNECTING
    assert profile_state("failed", False) == State.ERROR


def test_overall_prioriza_conectada():
    assert overall_state({"a": State.OFF, "b": State.ON, "c": State.ERROR}) == State.ON
    assert overall_state({"a": State.CONNECTING, "b": State.ERROR}) == State.CONNECTING
    assert overall_state({"a": State.ERROR}) == State.ERROR
    assert overall_state({"a": State.OFF}) == State.OFF
    assert overall_state({}, external=True) == State.ON


def test_state_rotulos():
    assert State.ON.label == "conectada" and State.ON.dot == "●"
    assert State("connecting") is State.CONNECTING


# ---------------------------------------------------------------- validação
BASE = NewProfile(name="nova", host="vpn.example.com")


def with_(**kw):
    return NewProfile(**{**BASE.to_dict(), **kw})


def test_valida_ok():
    assert validate_new_profile(BASE, {}) is None


@pytest.mark.parametrize("bad", ["", "Work", "../x", "a b", "x" * 33, "-x"])
def test_valida_nome(bad):
    assert validate_new_profile(with_(name=bad), {})


def test_valida_duplicado():
    assert "Já existe" in validate_new_profile(BASE, {"nova": None})


@pytest.mark.parametrize(
    "kw",
    [
        {"host": "x; rm -rf /"},
        {"host": ""},
        {"port": 0},
        {"port": 70000},
        {"auth": "outro"},
        {"auth": "password"},
        {"trusted_cert": "abc"},
        {"realm": "x\npppd-plugin = /tmp/a.so"},
    ],
)
def test_valida_recusa(kw):
    assert validate_new_profile(with_(**kw), {})


def test_valida_senha_e_cert_ok():
    assert validate_new_profile(with_(auth="password", username="u", password="p"), {}) is None
    assert validate_new_profile(with_(trusted_cert="AB:" * 31 + "AB" + "ab"), {}) is not None
    assert validate_new_profile(with_(trusted_cert="AB" * 32), {}) is None


# ---------------------------------------------------------- escolha de perfil
def test_pick_profile():
    profiles = {"a": 1, "b": 2}
    assert pick_profile("b", profiles, "a") == "b"
    assert pick_profile(None, profiles, "b") == "b"
    assert pick_profile(None, profiles, "zzz") == "a"
    assert pick_profile(None, profiles, None, active=["b"]) == "b"
    with pytest.raises(LookupError, match="não existe"):
        pick_profile("x", profiles, None)
    with pytest.raises(LookupError, match="Nenhuma VPN ativa"):
        pick_profile(None, profiles, None, active=[])
    with pytest.raises(LookupError, match="Nenhuma VPN cadastrada"):
        pick_profile(None, {}, None)


# --------------------------------------------------------------- settings
def test_settings_ida_e_volta_preserva_chaves_desconhecidas():
    s = Settings.from_dict({"default": "work", "agents": {"allow_connect": False}, "futura": {"x": 1}})
    assert s.agents == AgentPermissions(enabled=True, allow_connect=False, allow_disconnect=True)
    assert s.to_dict()["futura"] == {"x": 1}
    assert Settings.from_dict(s.to_dict()) == s


# ------------------------------------------------------------ openfortivpn
def test_parse_args_file():
    text = "# comentario\n\nEXTRA_ARGS=--saml-login\nVPN_HOST = vpn.example.net\n"
    assert parse_args_file(text) == {"EXTRA_ARGS": "--saml-login", "VPN_HOST": "vpn.example.net"}


def test_parse_conf_so_chaves_suportadas():
    p, ignored = parse_conf(
        "host = vpn.example.net:8443\nrealm = r1\n"
        "trusted-cert = " + "a" * 64 + "\ntrusted-cert = " + "b" * 64 + "\n"
        "pppd-plugin = /x.so\nusername = alice\npassword = s3nh4\n",
        "a",
    )
    assert (p.host, p.port, p.auth, p.realm) == ("vpn.example.net", 8443, "password", "r1")
    assert p.trusted_cert == "a" * 64
    assert ignored == ["pppd-plugin"], "pppd-plugin nunca é importado"


def test_summarize_log():
    info = summarize(
        [
            "INFO:   Authenticate at 'https://vpn/saml'",
            "ERROR:  Gateway certificate validation failed.",
            "    trusted-cert = " + "c" * 64,
            "INFO:   Tunnel is up and running.",
        ]
    )
    assert info.auth_url == "https://vpn/saml" and info.tunnel_up
    assert info.untrusted_cert == "c" * 64
    assert info.last_error.startswith("Gateway certificate")


def test_log_session_ao_vivo_dispara_eventos_uma_vez():
    events = []
    s = LogSession("work", "inv1", True, lambda k, _s: events.append(k))
    for line in [
        "INFO:   Authenticate at 'https://vpn/saml'",
        "INFO:   Authenticate at 'https://vpn/saml'",
        "INFO:   Tunnel is up and running.",
    ]:
        s.feed(line)
    assert [e for e in events if e != "changed"] == ["auth", "up"]


def test_log_session_relida_nao_dispara():
    events = []
    s = LogSession("work", "inv1", False, lambda k, _s: events.append(k))
    s.feed("INFO:   Authenticate at 'https://vpn/saml'")
    s.feed("INFO:   Tunnel is up and running.")
    assert s.info.tunnel_up and set(events) == {"changed"}


def test_public_dict_nunca_tem_a_senha():
    p = NewProfile("w", "vpn.example.com", auth="password", username="alice", password="s3nh4")
    shown = p.public_dict()
    assert "password" not in shown and shown["password_set"] is True
    assert "s3nh4" not in repr(shown)
