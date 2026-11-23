"""Apresentação do ícone (menu e tooltip como dados)."""

from vpntray.domain.model import SessionInfo, State
from vpntray.entrypoints.tray.presenter import menu_spec, tooltip_for


def labels(spec):
    return [e[1] for e in spec if e[0] in ("item", "label")]


def actions(spec):
    return [e[2] for e in spec if e[0] == "item"]


def test_tooltip():
    assert tooltip_for(State.ON, {"work": State.ON}, "work") == "VPN conectada (work)"
    assert "aguardando login" in tooltip_for(State.CONNECTING, {"work": State.CONNECTING}, "work", True)
    assert "clique para conectar (work)" in tooltip_for(State.OFF, {"work": State.OFF}, "work")
    assert "fora do app" in tooltip_for(State.ON, {}, None, external=True)
    assert "nenhuma cadastrada" in tooltip_for(State.OFF, {}, None)


def test_menu_desconectada():
    spec = menu_spec(["work"], {"work": State.OFF}, "work", {})
    assert ("connect", "work") in actions(spec) and ("disconnect", "work") not in actions(spec)
    assert any("work ★ — desconectada" in lbl for lbl in labels(spec))


def test_menu_conectada():
    spec = menu_spec(["work"], {"work": State.ON}, "work", {"work": SessionInfo(tunnel_up=True)})
    assert ("disconnect", "work") in actions(spec) and ("connect", "work") not in actions(spec)


def test_menu_aguardando_login():
    spec = menu_spec(
        ["work"], {"work": State.CONNECTING}, "work", {"work": SessionInfo(auth_url="https://vpn/x")}
    )
    assert ("open_url", "https://vpn/x") in actions(spec)
    assert "Cancelar conexão work" in labels(spec)


def test_menu_erro_certificado():
    info = {"x": SessionInfo(untrusted_cert="ab" * 32, last_error="Gateway certificate failed")}
    spec = menu_spec(["x"], {"x": State.ERROR}, "x", info)
    assert ("trust_cert", "x", "ab" * 32) in actions(spec)
    assert any(lbl.startswith("Erro: Gateway") for lbl in labels(spec))
    assert ("connect", "x") in actions(spec)


def test_menu_fixos_e_submenus():
    spec = menu_spec(["work"], {"work": State.OFF}, "work", {})
    assert ("add",) in actions(spec) and ("quit",) in actions(spec)
    subs = {e[1]: e[2] for e in spec if e[0] == "submenu"}
    assert subs["Ver log"] == [("item", "work", ("log", "work"))]
    assert next(c[1] for c in subs["Segurança"]).startswith("Pedir senha ao conectar")


def test_menu_padrao_so_com_mais_de_uma():
    assert not any(e[0] == "radio" for e in menu_spec(["a"], {"a": State.OFF}, "a", {}))
    two = menu_spec(["a", "b"], {"a": State.OFF, "b": State.OFF}, "b", {})
    radio = next(e for e in two if e[0] == "radio")
    assert radio[2] == [("a", False, ("set_default", "a")), ("b", True, ("set_default", "b"))]


def test_menu_sem_vpns():
    spec = menu_spec([], {}, None, {})
    assert "Nenhuma VPN cadastrada" in labels(spec)
    assert [e[1] for e in spec if e[0] == "submenu"] == ["Segurança"]


def test_menu_estavel_para_mesmo_estado():
    """O ícone só recria o menu se o spec mudar; precisa ser comparável."""

    def make():
        return menu_spec(["work"], {"work": State.ON}, "work", {"work": SessionInfo(tunnel_up=True)})

    assert make() == make()
