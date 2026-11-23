#!/usr/bin/env python3
"""Teste visual: gera prints do menu real, da janela de log e do diálogo.

Usa o FakeBackend (não toca na VPN de verdade). Abre cada tela por um
instante e salva PNGs em tests/snapshots/ + um index.html lado a lado.

    python3 tests/visual_snapshots.py
"""
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import vpn_tray as vt  # noqa: E402
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

OUT = os.path.join(HERE, "snapshots")


def pump(ms=250):
    end = GLib.get_monotonic_time() + ms * 1000
    ctx = GLib.MainContext.default()
    while GLib.get_monotonic_time() < end:
        ctx.iteration(False)


def grab_window(gdk_window, path, widget=None):
    """Fotografa só a janela (sem a sombra/CSD, que mostraria o que está atrás)."""
    x, y = gdk_window.get_origin()[1:]
    w, h = gdk_window.get_width(), gdk_window.get_height()
    if widget is not None:
        a = widget.get_allocation()
        top = widget.get_toplevel().get_titlebar() if hasattr(widget.get_toplevel(), "get_titlebar") else None
        ty = top.get_allocation().y if top is not None and top.get_visible() else a.y
        x, y, w, h = x + a.x, y + ty, a.width, a.height + (a.y - ty)
    root = Gdk.get_default_root_window()
    pb = Gdk.pixbuf_get_from_window(root, x, y, w, h)
    pb.savev(path, "png", [], [])
    return path


def new_app(profiles=None):
    fake = vt.FakeBackend(profiles or {"work": {"VPN_AUTH": "saml"},
                                       "quebrada": {"VPN_AUTH": "saml"}})
    app = vt.VpnTray(backend=fake, app_id="br.local.vpntray.snap",
                     settings_path=os.path.join(OUT, ".settings.json"),
                     poll_seconds=0, notify=False)
    app.settings["default"] = "work"
    app.setup_ui()
    return app


def advance(app, cond, steps=10):
    for _ in range(steps):
        if cond():
            return
        app.backend.tick()
        app.poll()


def snap_menu(app, name):
    """Abre o Gtk.Menu de verdade (o mesmo do ícone) e fotografa."""
    anchor = Gtk.Window(type=Gtk.WindowType.POPUP)
    anchor.set_default_size(1, 1)
    anchor.move(200, 120)
    anchor.show_all()
    pump(150)
    menu = app.menu
    menu.popup_at_widget(anchor, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
    pump(400)
    top = menu.get_toplevel().get_window()
    path = grab_window(top, os.path.join(OUT, f"menu-{name}.png"), menu)
    menu.popdown()
    anchor.destroy()
    pump(150)
    return path


def icon_png(state):
    pb = GdkPixbuf.Pixbuf.new_from_file_at_size(vt.icon(state), 48, 48)
    path = os.path.join(OUT, f"icon-{state}.png")
    pb.savev(path, "png", [], [])
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    shots = []  # (título, arquivo, legenda)

    for st in (vt.OFF, vt.CONNECTING, vt.ON, vt.ERROR):
        icon_png(st)

    app = new_app()
    shots.append(("Desconectada", snap_menu(app, "1-desconectada"), app.tooltip, vt.OFF))

    app.run_action(("connect", "work"))
    advance(app, lambda: app.backend.opened)
    shots.append(("Aguardando login SAML", snap_menu(app, "2-aguardando-login"),
                  app.tooltip, app.state))

    advance(app, lambda: app.state == vt.ON)
    shots.append(("Conectada", snap_menu(app, "3-conectada"), app.tooltip, app.state))

    win = app.show_log("work")
    win.move(80, 80)
    pump(500)
    shots.append(("Janela “Ver log”", grab_window(win.get_window(),
                  os.path.join(OUT, "5-log.png"), win.get_child()), "journal ao vivo dentro do app", None))
    win.destroy()

    app.run_action(("connect", "quebrada"))
    advance(app, lambda: app.state == vt.ERROR)
    shots.append(("Erro de certificado", snap_menu(app, "4-erro-certificado"),
                  app.tooltip, app.state))

    dlg = app.build_add_dialog()
    dlg.move(80, 80)
    pump(500)
    shots.append(("Nova VPN (vazia)", grab_window(dlg.get_window(),
                  os.path.join(OUT, "6-adicionar-vazio.png"), dlg.get_child()), "Salvar desabilitado", None))
    dlg.widgets["name"].set_text("nova")
    dlg.widgets["host"].set_text("vpn.example.org")
    pump(300)
    shots.append(("Nova VPN (SAML)", grab_window(dlg.get_window(),
                  os.path.join(OUT, "7-adicionar-saml.png"), dlg.get_child()), "validação ao vivo", None))
    dlg.widgets["auth_password"].set_active(True)
    dlg.widgets["advanced"].set_expanded(True)
    pump(600)
    shots.append(("Nova VPN (usuário e senha + avançado)", grab_window(dlg.get_window(),
                  os.path.join(OUT, "8-adicionar-senha.png"), dlg.get_child()), "campos aparecem só nesse modo",
                  None))
    dlg.destroy()
    app.status = None
    pump(100)

    cards = []
    for title, path, caption, state in shots:
        ic = (f'<img class="ic" src="icon-{state}.png" alt="">' if state else "")
        cards.append(
            f'<figure><figcaption>{ic}<b>{html.escape(title)}</b><br>'
            f'<small>{html.escape(caption)}</small></figcaption>'
            f'<img src="{os.path.basename(path)}" alt=""></figure>')
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write("""<!doctype html><meta charset="utf-8"><title>VPN Tray — snapshots</title>
<style>body{font:14px system-ui;background:#f4f4f4;margin:16px}
main{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}
figure{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:0}
figcaption{margin-bottom:8px}.ic{width:24px;vertical-align:middle;margin-right:6px}
img{max-width:900px}</style><h1>VPN Tray — teste visual</h1><main>"""
                + "".join(cards) + "</main>")
    for _t, path, *_ in shots:
        print(path)
    print(os.path.join(OUT, "index.html"))


if __name__ == "__main__":
    main()
