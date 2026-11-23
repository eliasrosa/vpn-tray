"""Janela "Ver log": journal ao vivo dentro do próprio app."""

from __future__ import annotations

from gi.repository import GLib, Gtk, Pango

from ...domain.rules import unit_name


class LogWindow(Gtk.Window):
    """Log ao vivo de uma VPN, dentro do próprio app (não depende de terminal)."""

    MAX_LINES = 5000

    def __init__(self, follower, name: str, icon_path: str | None = None):
        super().__init__(title=f"VPN Tray — log de {name}")
        self.set_default_size(900, 480)
        try:
            if icon_path:
                self.set_icon_from_file(icon_path)
        except GLib.Error:
            pass  # sem leitor de SVG (librsvg2-common): a janela abre sem ícone
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        self.add(box)

        self.buffer = Gtk.TextBuffer()
        self.view = Gtk.TextView(
            buffer=self.buffer,
            editable=False,
            cursor_visible=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            monospace=True,
        )
        self.scroll = Gtk.ScrolledWindow(vexpand=True)
        self.scroll.add(self.view)
        box.pack_start(self.scroll, True, True, 0)

        bar = Gtk.Box(spacing=6)
        hint = Gtk.Label(
            label=f"journalctl -u {unit_name(name)} -f",
            xalign=0,
            selectable=True,
            ellipsize=Pango.EllipsizeMode.END,
        )
        hint.get_style_context().add_class("dim-label")
        bar.pack_start(hint, True, True, 0)
        close = Gtk.Button(label="Fechar")
        close.connect("clicked", lambda *_: self.destroy())
        copy = Gtk.Button(label="Copiar tudo")
        copy.connect("clicked", self._copy)
        bar.pack_end(close, False, False, 0)
        bar.pack_end(copy, False, False, 0)
        box.pack_start(bar, False, False, 0)

        self.handle = follower.follow_profile(name, self.append)
        self.connect("destroy", lambda *_: self.handle.close())

    def text(self):
        s, e = self.buffer.get_bounds()
        return self.buffer.get_text(s, e, False)

    def append(self, line):
        adj = self.scroll.get_vadjustment()
        at_bottom = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 20
        self.buffer.insert(self.buffer.get_end_iter(), line.rstrip("\n") + "\n")
        extra = self.buffer.get_line_count() - self.MAX_LINES
        if extra > 0:
            self.buffer.delete(self.buffer.get_start_iter(), self.buffer.get_iter_at_line(extra))
        if at_bottom:
            GLib.idle_add(self._scroll_end)

    def _scroll_end(self):
        self.view.scroll_to_iter(self.buffer.get_end_iter(), 0, False, 0, 1)
        return False

    def _copy(self, *_):
        Gtk.Clipboard.get_default(self.get_display()).set_text(self.text(), -1)
