#!/usr/bin/env python3
"""Teste visual: prints do menu real, da janela de log e do formulário.

Usa o sistema em memória (não toca na VPN de verdade) e salva PNGs em
tests/snapshots/ (fora do git) + um index.html lado a lado.

    python3 tests/visual_snapshots.py
"""

import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from vpntray.adapters.memory import MemorySystem  # noqa: E402
from vpntray.composition import build_memory  # noqa: E402
from vpntray.domain.model import State  # noqa: E402
from vpntray.entrypoints.tray.app import VpnTrayApp, icon  # noqa: E402
from vpntray.entrypoints.tray.gtk_io import inline_runner  # noqa: E402

OUT = os.path.join(HERE, "snapshots")


def pump(ms=250):
    end = GLib.get_monotonic_time() + ms * 1000
    ctx = GLib.MainContext.default()
    while GLib.get_monotonic_time() < end:
        ctx.iteration(False)


def grab(gdk_window, path, widget=None):
    """Fotografa só a janela/menu (sem a sombra, que mostraria o que está atrás)."""
    x, y = gdk_window.get_origin()[1:]
    w, h = gdk_window.get_width(), gdk_window.get_height()
    if widget is not None:
        a = widget.get_allocation()
        top = widget.get_toplevel()
        title = top.get_titlebar() if hasattr(top, "get_titlebar") else None
        ty = title.get_allocation().y if title is not None and title.get_visible() else a.y
        x, y, w, h = x + a.x, y + ty, a.width, a.height + (a.y - ty)
    pb = Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), x, y, w, h)
    pb.savev(path, "png", [], [])
    return path


def advance(app, system, cond, steps=10):
    for _ in range(steps):
        if cond():
            return
        system.tick()
        app.poll()


def snap_menu(app, name):
    anchor = Gtk.Window(type=Gtk.WindowType.POPUP)
    anchor.set_default_size(1, 1)
    anchor.move(200, 120)
    anchor.show_all()
    pump(150)
    app.menu.popup_at_widget(anchor, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
    pump(400)
    path = grab(app.menu.get_toplevel().get_window(), os.path.join(OUT, f"menu-{name}.png"), app.menu)
    app.menu.popdown()
    anchor.destroy()
    pump(150)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    for st in (State.OFF, State.CONNECTING, State.ON, State.ERROR):
        GdkPixbuf.Pixbuf.new_from_file_at_size(icon(st), 48, 48).savev(
            os.path.join(OUT, f"icon-{st.value}.png"), "png", [], []
        )

    system = MemorySystem({"work": "saml", "quebrada": "saml"})
    container = build_memory(system)
    container.preferences.set_default("work")
    app = VpnTrayApp(
        container, system, app_id="br.local.vpntray.snap", poll_seconds=0, notify=False, runner=inline_runner
    )
    app.setup_ui()
    shots = [("Desconectada", snap_menu(app, "1-desconectada"), app.tooltip, State.OFF)]

    app.run_action(("connect", "work"))
    advance(app, system, lambda: system.opened)
    shots.append(("Aguardando login SAML", snap_menu(app, "2-aguardando-login"), app.tooltip, app.state))
    advance(app, system, lambda: app.state == State.ON)
    shots.append(("Conectada", snap_menu(app, "3-conectada"), app.tooltip, app.state))

    win = app.show_log("work")
    win.move(80, 80)
    pump(500)
    shots.append(
        (
            "Ver log",
            grab(win.get_window(), os.path.join(OUT, "5-log.png"), win.get_child()),
            "journal ao vivo",
            None,
        )
    )
    win.destroy()

    app.run_action(("connect", "quebrada"))
    advance(app, system, lambda: app.state == State.ERROR)
    shots.append(("Erro de certificado", snap_menu(app, "4-erro-certificado"), app.tooltip, app.state))

    dlg = app.build_add_dialog()
    dlg.move(80, 80)
    pump(500)
    shots.append(
        (
            "Nova VPN (vazia)",
            grab(dlg.get_window(), os.path.join(OUT, "6-adicionar-vazio.png"), dlg.get_child()),
            "Salvar desabilitado",
            None,
        )
    )
    dlg.widgets["name"].set_text("nova")
    dlg.widgets["host"].set_text("vpn.example.org")
    pump(300)
    shots.append(
        (
            "Nova VPN (SAML)",
            grab(dlg.get_window(), os.path.join(OUT, "7-adicionar-saml.png"), dlg.get_child()),
            "validação ao vivo",
            None,
        )
    )
    dlg.widgets["auth_password"].set_active(True)
    dlg.widgets["advanced"].set_expanded(True)
    pump(600)
    shots.append(
        (
            "Nova VPN (usuário e senha)",
            grab(dlg.get_window(), os.path.join(OUT, "8-adicionar-senha.png"), dlg.get_child()),
            "campos só nesse modo",
            None,
        )
    )
    dlg.destroy()
    app.status = None
    pump(100)

    cards = "".join(
        f"<figure><figcaption>{f'<img class=ic src=icon-{st.value}.png>' if st else ''}"
        f"<b>{html.escape(t)}</b><br><small>{html.escape(c)}</small></figcaption>"
        f'<img src="{os.path.basename(p)}"></figure>'
        for t, p, c, st in shots
    )
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(
            '<!doctype html><meta charset="utf-8"><title>VPN Tray — snapshots</title>'
            "<style>body{font:14px system-ui;background:#f4f4f4;margin:16px}"
            "main{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}"
            "figure{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:0}"
            ".ic{width:24px;vertical-align:middle;margin-right:6px}</style>"
            f"<h1>VPN Tray — teste visual</h1><main>{cards}</main>"
        )
    for _t, p, *_ in shots:
        print(p)


if __name__ == "__main__":
    main()
