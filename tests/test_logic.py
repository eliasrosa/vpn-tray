"""Lógica pura: sem GTK na tela, sem sistema."""
import vpn_tray as vt
from vpn_tray import CONNECTING, ERROR, OFF, ON


def labels(spec):
    return [e[1] for e in spec if e[0] in ("item", "label")]


def actions(spec):
    return [e[2] for e in spec if e[0] == "item"]


# ------------------------------------------------------------ parsers
def test_parse_args_file_ignora_comentario_e_linha_vazia():
    text = "# comentario\n\nEXTRA_ARGS=--saml-login\nVPN_HOST = vpn.example.net\n"
    assert vt.parse_args_file(text) == {"EXTRA_ARGS": "--saml-login", "VPN_HOST": "vpn.example.net"}


def test_parse_unit_show_varias_units():
    out = ("Id=vpn-tray@work.service\nActiveState=active\nInvocationID=abc\n\n"
           "Id=vpn-tray@outra-vpn.service\nActiveState=inactive\nInvocationID=\n")
    r = vt.parse_unit_show(out)
    assert r["work"] == {"Id": "vpn-tray@work.service", "ActiveState": "active",
                          "InvocationID": "abc"}
    assert r["outra-vpn"]["ActiveState"] == "inactive"


def test_parse_unit_show_ignora_outras_units():
    assert vt.parse_unit_show("Id=ssh.service\nActiveState=active\n") == {}


# ------------------------------------------------------------- estados
def test_profile_state():
    assert vt.profile_state("inactive", False) == OFF
    assert vt.profile_state("activating", False) == CONNECTING
    assert vt.profile_state("active", False) == CONNECTING   # aguardando SAML
    assert vt.profile_state("active", True) == ON
    assert vt.profile_state("deactivating", True) == CONNECTING
    assert vt.profile_state("failed", False) == ERROR


def test_overall_prioriza_conectada():
    assert vt.overall_state({"a": OFF, "b": ON, "c": ERROR}) == ON
    assert vt.overall_state({"a": CONNECTING, "b": ERROR}) == CONNECTING
    assert vt.overall_state({"a": ERROR}) == ERROR
    assert vt.overall_state({"a": OFF}) == OFF
    assert vt.overall_state({}, external=True) == ON


def test_tooltip_textos():
    assert vt.tooltip_for(ON, {"work": ON}, "work") == "VPN conectada (work)"
    assert "aguardando login" in vt.tooltip_for(CONNECTING, {"work": CONNECTING}, "work", True)
    assert "clique para conectar (work)" in vt.tooltip_for(OFF, {"work": OFF}, "work")
    assert "fora do app" in vt.tooltip_for(ON, {}, None, external=True)
    assert "nenhuma cadastrada" in vt.tooltip_for(OFF, {}, None)


# ----------------------------------------------------------------- menu
def test_menu_desconectada_oferece_conectar():
    spec = vt.menu_spec(["work"], {"work": OFF}, "work", {})
    assert ("connect", "work") in actions(spec)
    assert ("disconnect", "work") not in actions(spec)
    assert any("work ★ — desconectada" in lbl for lbl in labels(spec))


def test_menu_conectada_oferece_desconectar():
    spec = vt.menu_spec(["work"], {"work": ON}, "work", {"work": {"tunnel_up": True}})
    assert ("disconnect", "work") in actions(spec)
    assert ("connect", "work") not in actions(spec)


def test_menu_aguardando_login_tem_abrir_navegador_e_cancelar():
    info = {"work": {"auth_url": "https://vpn/x", "tunnel_up": False}}
    spec = vt.menu_spec(["work"], {"work": CONNECTING}, "work", info)
    assert ("open_url", "https://vpn/x") in actions(spec)
    assert ("disconnect", "work") in actions(spec)
    assert "Cancelar conexão work" in labels(spec)


def test_menu_erro_mostra_erro_e_confiar_certificado():
    info = {"x": {"cert": "ab" * 32, "error": "Gateway certificate validation failed"}}
    spec = vt.menu_spec(["x"], {"x": ERROR}, "x", info)
    assert ("trust_cert", "x", "ab" * 32) in actions(spec)
    assert any(lbl.startswith("Erro: Gateway") for lbl in labels(spec))
    assert ("connect", "x") in actions(spec)  # dá para tentar de novo


def test_menu_sempre_tem_adicionar_log_e_sair():
    spec = vt.menu_spec(["work"], {"work": OFF}, "work", {})
    assert ("add",) in actions(spec)
    assert ("quit",) in actions(spec)
    log = next(e for e in spec if e[0] == "submenu" and e[1] == "Ver log")
    assert log[2] == [("item", "work", ("log", "work"))]


def test_menu_padrao_so_aparece_com_mais_de_uma_vpn():
    one = vt.menu_spec(["a"], {"a": OFF}, "a", {})
    two = vt.menu_spec(["a", "b"], {"a": OFF, "b": OFF}, "b", {})
    assert not any(e[0] == "radio" for e in one)
    radio = next(e for e in two if e[0] == "radio")
    assert radio[2] == [("a", False, ("set_default", "a")), ("b", True, ("set_default", "b"))]


def test_menu_sem_vpns():
    spec = vt.menu_spec([], {}, None, {})
    assert "Nenhuma VPN cadastrada" in labels(spec)
    subs = [e[1] for e in spec if e[0] == "submenu"]
    assert subs == ["Segurança"]  # sem "Ver log"/"Remover" quando não há VPN


def test_menu_igual_para_mesmo_estado():
    """O app só recria o menu se o spec mudar; precisa ser comparável."""
    a = vt.menu_spec(["work"], {"work": ON}, "work", {"work": {"tunnel_up": True}})
    b = vt.menu_spec(["work"], {"work": ON}, "work", {"work": {"tunnel_up": True}})
    assert a == b


# ------------------------------------------------------------ validação
BASE = {"name": "nova", "host": "vpn.example.net", "port": 443, "auth": "saml"}


def test_valida_ok():
    assert vt.validate_new_profile(BASE, {}) is None


def test_valida_nome():
    for bad in ["", "Work", "../x", "a b", "x" * 33, "-x"]:
        assert vt.validate_new_profile({**BASE, "name": bad}, {}), bad


def test_valida_duplicado():
    assert "Já existe" in vt.validate_new_profile(BASE, {"nova": {}})


def test_valida_host_e_porta():
    assert vt.validate_new_profile({**BASE, "host": "x; rm -rf /"}, {})
    assert vt.validate_new_profile({**BASE, "port": 0}, {})
    assert vt.validate_new_profile({**BASE, "port": 70000}, {})


def test_valida_senha_obrigatoria():
    assert vt.validate_new_profile({**BASE, "auth": "password"}, {})
    assert vt.validate_new_profile({**BASE, "auth": "password", "username": "u",
                                    "password": "p"}, {}) is None


def test_valida_bloqueia_quebra_de_linha():
    # quebra de linha permitiria injetar "pppd-plugin = ..." no .conf
    assert vt.validate_new_profile({**BASE, "realm": "x\npppd-plugin = /tmp/a.so"}, {})


def test_valida_cert():
    assert vt.validate_new_profile({**BASE, "trusted_cert": "abc"}, {})
    assert vt.validate_new_profile({**BASE, "trusted_cert": "AB" * 32}, {}) is None


# --------------------------------------------------------------- sessão
def test_sessao_ao_vivo_dispara_eventos_uma_vez():
    events = []
    s = vt.Session("work", "inv1", True, lambda k, _s: events.append(k))
    for line in ["INFO:   Authenticate at 'https://vpn/saml'",
                 "INFO:   Authenticate at 'https://vpn/saml'",
                 "INFO:   Tunnel is up and running."]:
        s.feed(line)
    assert s.auth_url == "https://vpn/saml" and s.tunnel_up
    assert [e for e in events if e != "changed"] == ["auth", "up"]


def test_sessao_relida_nao_reabre_navegador():
    events = []
    s = vt.Session("work", "inv1", False, lambda k, _s: events.append(k))
    s.feed("INFO:   Authenticate at 'https://vpn/saml'")
    s.feed("INFO:   Tunnel is up and running.")
    assert s.tunnel_up
    assert set(events) == {"changed"}


def test_sessao_certificado_e_erro():
    s = vt.Session("x", "i", True, lambda *_: None)
    s.feed("ERROR:  Gateway certificate validation failed, and the certificate digest is "
           "not in the local whitelist.")
    s.feed("    trusted-cert = " + "c" * 64)
    assert s.untrusted_cert == "c" * 64
    assert s.last_error.startswith("Gateway certificate validation failed")
