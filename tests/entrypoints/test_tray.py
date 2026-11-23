"""Ícone GTK de verdade com o sistema em memória (precisa de tela)."""

import gi
import pytest
from conftest import needs_display

gi.require_version("Gtk", "3.0")
pytestmark = needs_display

from gi.repository import GLib, Gtk  # noqa: E402

from vpntray.domain.model import State  # noqa: E402
from vpntray.entrypoints.tray.app import VpnTrayApp  # noqa: E402
from vpntray.entrypoints.tray.gtk_io import inline_runner  # noqa: E402
from vpntray.entrypoints.tray.log_window import LogWindow  # noqa: E402


@pytest.fixture
def app(container, system):
    container.preferences.set_default("work")
    a = VpnTrayApp(
        container, system, app_id="br.local.vpntray.test", poll_seconds=0, notify=False, runner=inline_runner
    )
    a.setup_ui()
    yield a
    for w in list(a.log_windows.values()):
        w.destroy()
    a.status = None


def labels(menu):
    return [
        c.get_label()
        for c in menu.get_children()
        if isinstance(c, Gtk.MenuItem) and not isinstance(c, Gtk.SeparatorMenuItem)
    ]


def item(menu, label):
    return next(c for c in menu.get_children() if isinstance(c, Gtk.MenuItem) and c.get_label() == label)


def click(menu, label):
    mi = item(menu, label)
    assert mi.get_sensitive(), f"{label} não está clicável"
    mi.activate()


def tick_until(app, system, cond, steps=10):
    for _ in range(steps):
        if cond():
            return True
        system.tick()
        app.poll()
    return cond()


# ---------------------------------------------------------------- clique
def test_clique_no_icone_so_abre_menu(app, system):
    """Requisito: clicar no ícone não pode conectar nem desconectar."""
    assert app.status.get_primary_menu() is app.menu  # esquerdo -> menu
    assert app.status.get_secondary_menu() is app.menu  # direito  -> menu
    app.status.emit("activate", 1, 0)
    app.status.emit("button-release-event", 0, 0, 1, 0, 0)
    assert system.calls == []


def test_estado_inicial(app):
    assert app.state == State.OFF and app.icon_path.endswith("vpn-off.svg")
    assert "clique para conectar (work)" in app.tooltip


# ---------------------------------------------------------------- fluxo
def test_conectar_pelo_menu_ate_conectada(app, system):
    click(app.menu, "Conectar work")
    assert system.calls == [("start", "work")] and app.state == State.CONNECTING
    assert tick_until(app, system, lambda: system.opened)
    assert system.opened == ["https://vpn.work.example/remote/saml/start?redirect=1"]
    assert "Abrir login no navegador" in labels(app.menu) and "aguardando login" in app.tooltip
    assert tick_until(app, system, lambda: app.state == State.ON)
    assert app.icon_path.endswith("vpn-on.svg") and app.tooltip == "VPN conectada (work)"
    assert ("VPN work", "Conectada.") in app.notifications
    assert len(system.opened) == 1, "navegador abriu uma vez só"


def test_desconectar_pelo_menu(app, system):
    click(app.menu, "Conectar work")
    tick_until(app, system, lambda: app.state == State.ON)
    click(app.menu, "Desconectar work")
    assert system.calls[-1] == ("stop", "work") and app.state == State.OFF
    assert ("VPN work", "Desconectada.") in app.notifications


def test_menu_nao_e_recriado_sem_mudanca(app):
    menu = app.menu
    app.poll()
    app.poll()
    assert app.menu is menu, "menu recriado à toa fecharia o menu aberto"


def test_falha_de_certificado(app, system):
    click(app.menu, "Conectar quebrada")
    assert tick_until(app, system, lambda: app.state == State.ERROR)
    assert "Confiar no certificado e reconectar…" in labels(app.menu)
    assert app.icon_path.endswith("vpn-error.svg")


def test_senha_recusada_vira_aviso(app, system):
    system.deny_auth = True
    click(app.menu, "Conectar work")
    assert app.notifications[-1][0] == "VPN work: não conectou"
    assert app.state == State.OFF


def test_vpn_fora_do_app(app, system):
    system.external = True
    app.poll()
    assert app.state == State.ON and "openfortivpn rodando fora do app" in labels(app.menu)


# ------------------------------------------------------------------ log
def test_ver_log(app, system):
    click(app.menu, "Conectar work")
    tick_until(app, system, lambda: app.state == State.ON)
    log_item = item(app.menu, "Ver log")
    click(log_item.get_submenu(), "work")
    win = app.log_windows["work"]
    assert isinstance(win, LogWindow) and "Tunnel is up and running." in win.text()
    assert app.show_log("work") is win, "reaproveita a janela"
    system.tick()
    win.destroy()
    assert "work" not in app.log_windows


def test_log_abre_mesmo_sem_leitor_de_svg(app, monkeypatch):
    """Sem librsvg2-common o GdkPixbuf não lê SVG: a janela tem que abrir igual."""

    def boom(self, path):
        raise GLib.Error("Couldn't recognize the image file format")

    monkeypatch.setattr(LogWindow, "set_icon_from_file", boom)
    assert app.show_log("work").get_visible()


# ------------------------------------------------------- adicionar VPN
def test_dialogo_adicionar_e_salvar(app, system):
    dlg = app.build_add_dialog()
    w = dlg.widgets
    assert not w["save"].get_sensitive(), "Salvar começa desabilitado"
    w["name"].set_text("Nova")
    w["host"].set_text("vpn.example.org")
    assert w["save"].get_sensitive() and w["error"].get_text().startswith("Pronto: vpn-tray@nova")
    w["auth_password"].set_active(True)
    assert w["cred"].get_reveal_child() and not w["save"].get_sensitive()
    w["auth_saml"].set_active(True)
    w["default"].set_active(True)
    w["connect"].set_active(True)
    profile, flags = dlg.read()
    dlg.destroy()
    app.save_new_profile(profile, flags)
    assert ("admin", "add", "nova") in system.calls and "nova" in system.list()
    assert app.c.settings.load().default == "nova"
    assert system.calls[-1] == ("start", "nova"), "conectar depois de salvar"


def test_dialogo_valida_nome_existente(app):
    dlg = app.build_add_dialog()
    dlg.widgets["name"].set_text("work")
    dlg.widgets["host"].set_text("vpn.example.com")
    assert "Já existe" in dlg.widgets["error"].get_text()
    assert not dlg.widgets["save"].get_sensitive()
    dlg.destroy()


def test_dialogo_importa_conf(app):
    dlg = app.build_add_dialog()
    _p, ignored = dlg.import_text(
        "host = vpn.example.com\nport = 10443\nusername = alice\n"
        "password = x\ntrusted-cert = " + "ab" * 32 + "\nset-dns = 0\n",
        "/tmp/Empresa X.conf",
    )
    w = dlg.widgets
    assert w["name"].get_text() == "empresa-x" and int(w["port"].get_value()) == 10443
    assert w["auth_password"].get_active() and w["advanced"].get_expanded()
    assert ignored == ["set-dns"] and "set-dns" in w["error"].get_text()
    dlg.destroy()


# ------------------------------------------------------------ segurança
def test_menu_seguranca_e_toggles(app, system):
    seg = item(app.menu, "Segurança").get_submenu()
    checks = {c.get_label(): c.get_active() for c in seg.get_children()}
    assert checks["Pedir senha ao conectar (vale para app, CLI e agentes)"] is False
    assert checks["Agentes (MCP) podem conectar"] is True
    app.run_action(("toggle_require_password",))
    assert system.calls[-1] == ("admin", "policy", True)
    app.run_action(("toggle_agents", "allow_connect"))
    assert app.c.settings.load().agents.allow_connect is False


def test_padrao_e_autoconnect(app):
    app.run_action(("set_default", "quebrada"))
    app.run_action(("toggle_autoconnect",))
    s = app.c.settings.load()
    assert s.default == "quebrada" and s.autoconnect
    assert any("quebrada ★" in lbl for lbl in labels(app.menu))
