"""App de verdade (GTK) com o sistema de mentira (FakeBackend)."""
import os

import pytest

from conftest import needs_display
import vpn_tray as vt
from vpn_tray import CONNECTING, ERROR, OFF, ON

pytestmark = needs_display

from gi.repository import Gtk  # noqa: E402

_counter = [0]


def run_until(cond, loops=200):
    ctx = vt.GLib.MainContext.default()
    for _ in range(loops):
        if cond():
            return True
        ctx.iteration(False)
    return cond()


@pytest.fixture
def app(tmp_path):
    """App registrado (do_startup rodou: ícone + menu), sem notificações reais."""
    fake = vt.FakeBackend({"work": {"VPN_AUTH": "saml"}, "quebrada": {"VPN_AUTH": "saml"}})
    _counter[0] += 1
    a = vt.VpnTray(backend=fake, app_id=f"br.local.vpntray.test{os.getpid()}x{_counter[0]}",
                   settings_path=str(tmp_path / "settings.json"), poll_seconds=0,
                   notify=False)
    a.settings["default"] = "work"
    a.setup_ui()  # o mesmo que o do_startup monta (ícone, menu, 1º poll)
    yield a
    for w in list(a.log_windows.values()):
        w.destroy()
    a.status = None  # some com o ícone do painel


def menu_labels(menu):
    return [c.get_label() for c in menu.get_children() if isinstance(c, Gtk.MenuItem)
            and not isinstance(c, Gtk.SeparatorMenuItem)]


def click(menu, label):
    item = next(c for c in menu.get_children()
                if isinstance(c, Gtk.MenuItem) and c.get_label() == label)
    assert item.get_sensitive(), f"{label} não está clicável"
    item.activate()


def tick_until(app, cond, steps=10):
    for _ in range(steps):
        if cond():
            return True
        app.backend.tick()
        app.poll()
    return cond()


# ------------------------------------------------------ clique no ícone
def test_clique_esquerdo_so_abre_menu(app):
    """Requisito: clicar no ícone não pode conectar/desconectar."""
    assert app.status is not None
    assert app.status.get_primary_menu() is app.menu     # esquerdo -> menu
    assert app.status.get_secondary_menu() is app.menu   # direito  -> menu
    assert not hasattr(app, "_on_left_click")
    # simula o clique esquerdo do painel: nenhum systemctl é chamado
    app.status.emit("activate", 1, 0)
    app.status.emit("button-release-event", 0, 0, 1, 0, 0)
    assert app.backend.calls == []


def test_icone_e_tooltip_iniciais(app):
    assert app.state == OFF
    assert app.icon_path.endswith("vpn-off.svg")
    assert "clique para conectar (work)" in app.tooltip


# ----------------------------------------------------- fluxo de conexão
def test_conectar_pelo_menu_saml_ate_conectada(app):
    click(app.menu, "Conectar work")
    assert app.backend.calls == [("start", "work")]
    assert app.state == CONNECTING

    assert tick_until(app, lambda: app.backend.opened)
    assert app.backend.opened == ["https://vpn.work.example/remote/saml/start?redirect=1"]
    assert "Abrir login no navegador" in menu_labels(app.menu)
    assert "aguardando login" in app.tooltip

    assert tick_until(app, lambda: app.state == ON)
    assert app.icon_path.endswith("vpn-on.svg")
    assert app.tooltip == "VPN conectada (work)"
    assert "Desconectar work" in menu_labels(app.menu)
    assert ("VPN work", "Conectada.") in app.notifications
    assert len(app.backend.opened) == 1, "navegador abriu mais de uma vez"


def test_desconectar_pelo_menu(app):
    click(app.menu, "Conectar work")
    tick_until(app, lambda: app.state == ON)
    click(app.menu, "Desconectar work")
    assert app.backend.calls[-1] == ("stop", "work")
    assert app.state == OFF
    assert ("VPN work", "Desconectada.") in app.notifications


def test_reabrir_app_com_vpn_ligada_nao_reabre_navegador(app, tmp_path):
    click(app.menu, "Conectar work")
    tick_until(app, lambda: app.state == ON)
    # "reinicia" o app usando o mesmo backend (VPN continua no ar)
    app2 = vt.VpnTray(backend=app.backend, app_id=app.get_application_id() + "b",
                      settings_path=str(tmp_path / "s2.json"), poll_seconds=0, notify=False)
    app2.setup_ui()
    assert app2.state == ON
    assert len(app.backend.opened) == 1
    assert app2.notifications == []
    app2.status = None


def test_menu_nao_e_recriado_sem_mudanca(app):
    menu = app.menu
    app.poll()
    app.poll()
    assert app.menu is menu, "menu recriado à toa fecharia o menu aberto"


def test_falha_de_certificado(app):
    click(app.menu, "Conectar quebrada")
    assert tick_until(app, lambda: app.state == ERROR)
    labels = menu_labels(app.menu)
    assert "Confiar no certificado e reconectar…" in labels
    assert any(lbl.startswith("Erro: Gateway certificate") for lbl in labels)
    assert app.icon_path.endswith("vpn-error.svg")


def test_conectar_outra_derruba_a_atual(app):
    click(app.menu, "Conectar work")
    tick_until(app, lambda: app.state == ON)
    app.run_action(("connect", "quebrada"))
    assert ("stop", "work") in app.backend.calls
    assert app.backend.calls[-1] == ("start", "quebrada")


def test_vpn_fora_do_app(app):
    app.backend.external = True
    app.poll()
    assert app.state == ON
    assert "openfortivpn rodando fora do app (alias?)" in menu_labels(app.menu)


# ------------------------------------------------------------ log
def test_ver_log_abre_janela_com_linhas(app):
    click(app.menu, "Conectar work")
    tick_until(app, lambda: app.state == ON)
    win = app.show_log("work")
    assert isinstance(win, vt.LogWindow) and win.get_visible()
    assert "Tunnel is up and running." in win.text()
    assert app.show_log("work") is win, "segunda vez reaproveita a janela"
    win.destroy()
    assert "work" not in app.log_windows


def test_log_abre_mesmo_sem_leitor_de_svg(app, monkeypatch):
    """Sem librsvg2-common o GdkPixbuf não lê SVG: a janela tem que abrir igual."""
    def boom(self, path):
        raise vt.GLib.Error("Couldn't recognize the image file format")
    monkeypatch.setattr(vt.LogWindow, "set_icon_from_file", boom)
    win = app.show_log("work")
    assert win.get_visible()


def test_log_continua_recebendo_linhas(app):
    lines = []
    app.backend.follow_log = lambda name, cb: (lines.append(cb), vt.FakeHandle())[1]
    win = app.show_log("work")
    lines[0]("INFO:   linha nova")
    assert win.text().endswith("INFO:   linha nova\n")


def test_item_ver_log_do_menu_funciona(app):
    log_item = next(c for c in app.menu.get_children()
                    if isinstance(c, Gtk.MenuItem) and c.get_label() == "Ver log")
    click(log_item.get_submenu(), "work")
    assert "work" in app.log_windows


# ---------------------------------------------------- adicionar / padrão
def test_dialogo_adicionar_e_salvar(app):
    dlg = app.build_add_dialog()
    w = dlg.widgets
    assert not w["save"].get_sensitive(), "Salvar começa desabilitado"
    w["name"].set_text("Nova")
    w["host"].set_text("vpn.example.org")
    assert w["save"].get_sensitive()
    assert w["error"].get_text().startswith("Pronto: vpn-tray@nova")
    # SAML: usuário/senha escondidos; senha: aparecem e viram obrigatórios
    assert not w["cred"].get_reveal_child()
    w["auth_password"].set_active(True)
    assert w["cred"].get_reveal_child()
    assert not w["save"].get_sensitive()
    assert "usuário e senha" in w["error"].get_text().lower()
    w["auth_saml"].set_active(True)
    w["default"].set_active(True)
    w["connect"].set_active(True)
    data, flags = dlg.read()
    dlg.destroy()
    assert data["name"] == "nova" and data["port"] == 443 and data["auth"] == "saml"
    app.save_new_profile(data, flags)
    assert ("helper", ("add",)) in app.backend.calls
    assert "nova" in app.profiles
    assert app.settings["default"] == "nova"
    assert app.backend.calls[-1] == ("start", "nova"), "conectar depois de salvar"


def test_dialogo_validacao_ao_vivo_nome_invalido(app):
    dlg = app.build_add_dialog()
    dlg.widgets["name"].set_text("work")  # já existe
    dlg.widgets["host"].set_text("vpn.example.net")
    assert "Já existe" in dlg.widgets["error"].get_text()
    assert not dlg.widgets["save"].get_sensitive()
    dlg.destroy()


def test_dialogo_importa_conf_do_openfortivpn(app):
    dlg = app.build_add_dialog()
    data, ignored = dlg.import_text(
        "host = vpn.example.com\nport = 10443\nusername = joao\npassword = x\n"
        "trusted-cert = " + "ab" * 32 + "\nset-dns = 0\n", "/tmp/Empresa X.conf")
    w = dlg.widgets
    assert w["name"].get_text() == "empresa-x"
    assert w["host"].get_text() == "vpn.example.com"
    assert int(w["port"].get_value()) == 10443
    assert w["auth_password"].get_active() and w["cred"].get_reveal_child()
    assert w["advanced"].get_expanded()
    assert ignored == ["set-dns"] and "set-dns" in w["error"].get_text()
    dlg.destroy()


# ------------------------------------------------------------ segurança
def test_menu_seguranca_reflete_politica_e_agentes(app):
    seg = next(c for c in app.menu.get_children()
               if isinstance(c, Gtk.MenuItem) and c.get_label() == "Segurança")
    items = {c.get_label(): c.get_active() for c in seg.get_submenu().get_children()}
    assert items["Pedir senha ao conectar (vale para app, CLI e agentes)"] is False
    assert items["Agentes (MCP) podem conectar"] is True


def test_ligar_pedir_senha_chama_helper(app):
    app.run_action(("toggle_require_password",))
    assert app.backend.calls[-1] == ("helper", ("policy", "require-password", "on"))
    assert app.policy["require_password_connect"] is True
    app.run_action(("toggle_require_password",))
    assert app.backend.calls[-1] == ("helper", ("policy", "require-password", "off"))


def test_toggle_agentes_salva(app, tmp_path):
    app.run_action(("toggle_agents", "allow_connect"))
    assert vt.load_settings(str(tmp_path / "settings.json"))["agents"]["allow_connect"] is False


def test_conexao_iniciada_fora_do_app_abre_navegador(app):
    """Agente/CLI deu systemctl start: o ícone abre o login mesmo assim."""
    app.backend.systemctl("start", "work", lambda *a: None)  # não passou pelo app
    app.poll()
    assert tick_until(app, lambda: app.backend.opened)


def test_trocar_padrao_e_autoconnect_salvam(app, tmp_path):
    app.run_action(("set_default", "quebrada"))
    app.run_action(("toggle_autoconnect",))
    saved = vt.load_settings(str(tmp_path / "settings.json"))
    assert saved["default"] == "quebrada" and saved["autoconnect"] is True
    assert any("quebrada ★" in lbl for lbl in menu_labels(app.menu))
