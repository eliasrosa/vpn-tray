#!/usr/bin/env python3
"""VPN Tray — ícone ao lado do relógio para o openfortivpn.

Qualquer clique (esquerdo ou direito) abre o menu; conectar e desconectar
são sempre itens do menu, nunca o clique direto no ícone — assim um clique
sem querer não derruba a VPN nem abre o navegador.

A conexão roda como serviço systemd (vpn-tray@<perfil>.service); o app só
liga/desliga a unit e acompanha o journal dela (login SAML, túnel no ar,
certificado não confiável, erros).

Organização (para dar para testar):
  * funções puras: parse_*, overall_state, tooltip_for, menu_spec,
    validate_new_profile — sem GTK, sem sistema;
  * Backend / FakeBackend: tudo que toca o sistema (systemctl, journal,
    pkexec, navegador). Os testes e o modo --demo usam o FakeBackend;
  * VpnTray: a cola GTK (ícone, menu, diálogos, janela de log).
"""
import json
import os
import re
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gio, GLib, Gtk, Notify, Pango  # noqa: E402

try:
    gi.require_version("XApp", "1.0")
    from gi.repository import XApp  # noqa: E402
except (ValueError, ImportError):
    XApp = None

import vpnlib  # noqa: E402
from vpnlib import (  # noqa: E402,F401  (reexportados: testes usam vt.*)
    CONF_DIR, CONNECTING, DOT, ERROR, HASH_RE, HELPER, HOST_RE, LABEL, NAME_RE, OFF, ON,
    RE_AUTH, RE_CERT, RE_ERR, RE_UP, first_with, load_settings, menu_spec, overall_state,
    parse_args_file, parse_openfortivpn_conf, parse_unit_show, profile_state,
    save_settings, tooltip_for, unit_of, validate_new_profile)

APP_ID = vpnlib.APP_DBUS_NAME
HERE = os.path.dirname(os.path.realpath(__file__))
ICON_DIR = os.path.join(HERE, "icons")
CFG_FILE = vpnlib.CFG_FILE


def icon(state):
    return os.path.join(ICON_DIR, f"vpn-{state}.svg")


# ================================================================ sessão
class Session:
    """Acompanha uma execução (InvocationID) de uma unit pelo journal."""

    def __init__(self, name, invocation, live, events):
        self.name = name
        self.invocation = invocation
        # live=False: execução que já rodava quando o app abriu; o journal é
        # relido do início, então não reabre navegador nem notifica.
        self.live = live
        self.events = events  # callable(tipo, sessão)
        self.tunnel_up = False
        self.auth_url = None
        self.untrusted_cert = None
        self.last_error = None
        self.handle = None

    def feed(self, line):
        line = line.strip()
        m = RE_AUTH.search(line)
        if m and not self.auth_url:
            self.auth_url = m.group(1)
            self.live and self.events("auth", self)
        m = RE_CERT.search(line)
        if m and not self.untrusted_cert:
            self.untrusted_cert = m.group(1)
            self.live and self.events("cert", self)
        if RE_UP.search(line) and not self.tunnel_up:
            self.tunnel_up = True
            self.live and self.events("up", self)
        m = RE_ERR.search(line)
        if m:
            self.last_error = m.group(1).strip()
        self.events("changed", self)

    def info(self):
        return {"auth_url": self.auth_url, "tunnel_up": self.tunnel_up,
                "cert": self.untrusted_cert, "error": self.last_error}

    def close(self):
        if self.handle:
            self.handle.close()
            self.handle = None


# ================================================================ backends
class LineReader:
    """Lê stdout de um Gio.Subprocess linha a linha, sem travar a UI."""

    def __init__(self, argv, on_line):
        self.on_line = on_line
        self._buf = ""
        self.proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        self.stream = self.proc.get_stdout_pipe()
        self.cancel = Gio.Cancellable()
        self._read()

    def _read(self):
        self.stream.read_bytes_async(8192, GLib.PRIORITY_DEFAULT, self.cancel, self._on_data)

    def _on_data(self, stream, res):
        try:
            data = stream.read_bytes_finish(res).get_data()
        except GLib.Error:
            return
        if not data:
            return
        self._buf += data.decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for line in lines:
            self.on_line(line)
        self._read()

    def close(self):
        self.cancel.cancel()
        try:
            self.proc.force_exit()
        except GLib.Error:
            pass


def _run_async(argv, stdin_text, callback):
    flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    if stdin_text is not None:
        flags |= Gio.SubprocessFlags.STDIN_PIPE
    try:
        proc = Gio.Subprocess.new(argv, flags)
    except GLib.Error as e:
        callback(127, e.message)
        return

    def done(p, res):
        try:
            _ok, _out, err = p.communicate_utf8_finish(res)
        except GLib.Error as e:
            err = e.message
        callback(p.get_exit_status(), (err or "").strip())

    proc.communicate_utf8_async(stdin_text, None, done)


class Backend:
    """O sistema de verdade (a parte síncrona vem da vpnlib)."""

    def __init__(self, conf_dir=None):
        self.conf_dir = conf_dir or CONF_DIR

    def profiles(self):
        return vpnlib.list_profiles(self.conf_dir)

    def unit_props(self, names):
        if not names:
            return {}
        argv = ["systemctl", "show", "-p", "Id,ActiveState,InvocationID"]
        argv += [unit_of(n) for n in names]
        try:
            p = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE)
            _ok, out, _err = p.communicate_utf8(None, None)
        except GLib.Error:
            return {}
        return parse_unit_show(out or "")

    def external_running(self):
        return vpnlib.external_running()

    def policy(self):
        return vpnlib.load_policy()

    def follow_invocation(self, invocation, on_line):
        return LineReader(["journalctl", f"_SYSTEMD_INVOCATION_ID={invocation}",
                           "-f", "--lines=all", "-o", "cat", "--no-pager"], on_line)

    def follow_log(self, name, on_line):
        return LineReader(["journalctl", "-u", unit_of(name), "-n", "300",
                           "-f", "-o", "short-iso", "--no-pager"], on_line)

    def systemctl(self, verb, name, callback):
        _run_async(["systemctl", "--quiet", verb, unit_of(name)], None, callback)

    def helper(self, args, stdin_text, callback):
        if not os.path.exists(HELPER):
            callback(1, "VPN Tray não está instalado: rode o install.sh.")
            return
        _run_async(["pkexec", HELPER] + list(args), stdin_text, callback)

    def open_url(self, url):
        Gio.AppInfo.launch_default_for_uri(url, None)


class FakeHandle:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeBackend:
    """Sistema de mentira, para testes e para `vpn-tray --demo`.

    connect() simula: SAML -> login -> túnel no ar (em `steps` chamadas de
    tick()). Perfil chamado "quebrada" falha com certificado não confiável.
    """

    def __init__(self, profiles=None):
        self._profiles = profiles if profiles is not None else {
            "work": {"VPN_AUTH": "saml", "EXTRA_ARGS": "--saml-login"}}
        self.units = {}     # nome -> {"ActiveState", "InvocationID"}
        self.lines = {}     # invocation -> [linhas]
        self.readers = {}   # invocation -> [callbacks]
        self.calls = []     # histórico de ações (para os testes)
        self.opened = []
        self.external = False
        self.policy_state = {"require_password_connect": False}
        self._inv = 0
        self._script = {}   # nome -> linhas que ainda vão sair

    def profiles(self):
        return dict(self._profiles)

    def unit_props(self, names):
        return {n: dict(self.units.get(n, {"ActiveState": "inactive", "InvocationID": ""}))
                for n in names}

    def ppp_up(self):
        return any(u["ActiveState"] == "active" for u in self.units.values())

    def external_running(self):
        return self.external

    def policy(self):
        return dict(self.policy_state)

    def follow_invocation(self, invocation, on_line):
        for line in self.lines.get(invocation, []):
            on_line(line)
        self.readers.setdefault(invocation, []).append(on_line)
        return FakeHandle()

    def follow_log(self, name, on_line):
        inv = self.units.get(name, {}).get("InvocationID")
        for line in self.lines.get(inv, ["(sem log ainda)"]):
            on_line(line)
        return FakeHandle()

    def _emit(self, name, line):
        inv = self.units[name]["InvocationID"]
        self.lines.setdefault(inv, []).append(line)
        for cb in self.readers.get(inv, []):
            cb(line)

    def systemctl(self, verb, name, callback):
        self.calls.append((verb, name))
        if verb == "start":
            self._inv += 1
            self.units[name] = {"ActiveState": "activating", "InvocationID": f"inv{self._inv}"}
            if name == "quebrada":
                self._script[name] = [
                    "ERROR:  Gateway certificate validation failed.",
                    "    trusted-cert = " + "ab" * 32, "__fail__"]
            else:
                self._script[name] = [
                    "INFO:   Listening for SAML login on port 8020",
                    f"INFO:   Authenticate at 'https://vpn.{name}.example/remote/saml/start?redirect=1'",
                    "__active__",
                    "INFO:   Authenticated.",
                    "INFO:   Tunnel is up and running."]
        elif verb == "stop":
            self._script.pop(name, None)
            if name in self.units:
                self.units[name]["ActiveState"] = "inactive"
        callback(0, "")

    def tick(self):
        """Avança um passo de cada conexão simulada."""
        for name, script in list(self._script.items()):
            if not script:
                del self._script[name]
                continue
            line = script.pop(0)
            if line == "__active__":
                self.units[name]["ActiveState"] = "active"
            elif line == "__fail__":
                self.units[name]["ActiveState"] = "failed"
            else:
                self._emit(name, line)
        return True

    def helper(self, args, stdin_text, callback):
        self.calls.append(("helper", tuple(args)))
        if args[0] == "add":
            data = json.loads(stdin_text)
            self._profiles[data["name"]] = {"VPN_AUTH": data["auth"]}
        elif args[0] == "remove":
            self._profiles.pop(args[1], None)
            self.units.pop(args[1], None)
        elif args[:2] == ["policy", "require-password"]:
            self.policy_state["require_password_connect"] = args[2] == "on"
        callback(0, "")

    def open_url(self, url):
        self.opened.append(url)


# ================================================================= GTK
class LogWindow(Gtk.Window):
    """Log ao vivo de uma VPN, dentro do próprio app (não depende de terminal)."""

    MAX_LINES = 5000

    def __init__(self, backend, name):
        super().__init__(title=f"VPN Tray — log de {name}")
        self.set_default_size(900, 480)
        try:
            self.set_icon_from_file(icon(ON))
        except GLib.Error:
            pass  # sem leitor de SVG (librsvg2-common): a janela abre sem ícone
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        self.add(box)

        self.buffer = Gtk.TextBuffer()
        self.view = Gtk.TextView(buffer=self.buffer, editable=False, cursor_visible=False,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True)
        self.scroll = Gtk.ScrolledWindow(vexpand=True)
        self.scroll.add(self.view)
        box.pack_start(self.scroll, True, True, 0)

        bar = Gtk.Box(spacing=6)
        hint = Gtk.Label(label=f"journalctl -u {unit_of(name)} -f", xalign=0,
                         selectable=True, ellipsize=Pango.EllipsizeMode.END)
        hint.get_style_context().add_class("dim-label")
        bar.pack_start(hint, True, True, 0)
        close = Gtk.Button(label="Fechar")
        close.connect("clicked", lambda *_: self.destroy())
        copy = Gtk.Button(label="Copiar tudo")
        copy.connect("clicked", self._copy)
        bar.pack_end(close, False, False, 0)
        bar.pack_end(copy, False, False, 0)
        box.pack_start(bar, False, False, 0)

        self.handle = backend.follow_log(name, self.append)
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
            self.buffer.delete(self.buffer.get_start_iter(),
                               self.buffer.get_iter_at_line(extra))
        if at_bottom:
            GLib.idle_add(self._scroll_end)

    def _scroll_end(self):
        self.view.scroll_to_iter(self.buffer.get_end_iter(), 0, False, 0, 1)
        return False

    def _copy(self, *_):
        Gtk.Clipboard.get_default(self.get_display()).set_text(self.text(), -1)

CSS = b"""
.vt-section { font-weight: bold; opacity: 0.75; margin-top: 6px; }
.vt-hint { opacity: 0.6; font-size: 90%; }
.vt-error { color: #d0453a; }
.vt-ok { color: #2f9e57; }
"""


class AddVpnDialog(Gtk.Dialog):
    """Formulário de nova VPN: seções, login como alternância, avançado
    recolhido, validação ao vivo e importação de .conf do openfortivpn."""

    def __init__(self, existing, parent=None):
        super().__init__(title="Nova VPN", use_header_bar=True, modal=True,
                         transient_for=parent)
        self.existing = existing
        self.set_default_size(480, -1)
        self.set_resizable(False)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        hb = self.get_header_bar()
        hb.set_subtitle("openfortivpn")
        self.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        save = self.add_button("Salvar", Gtk.ResponseType.OK)
        save.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)

        w = self.widgets = {"save": save}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_start=22, margin_end=22, margin_top=14, margin_bottom=18)
        self.get_content_area().add(box)

        # importar
        imp_row = Gtk.Box(spacing=8)
        imp_lbl = Gtk.Label(label="Já tem um arquivo de configuração?", xalign=0)
        imp_lbl.get_style_context().add_class("vt-hint")
        w["import"] = Gtk.Button(label="Importar .conf…")
        w["import"].connect("clicked", self._on_import)
        imp_row.pack_start(imp_lbl, True, True, 0)
        imp_row.pack_end(w["import"], False, False, 0)
        box.pack_start(imp_row, False, False, 0)

        # --- Conexão
        box.pack_start(self._section("Conexão"), False, False, 0)
        grid = self._grid()
        w["name"] = Gtk.Entry(placeholder_text="work", activates_default=True, hexpand=True)
        w["host"] = Gtk.Entry(placeholder_text="vpn.example.com", activates_default=True,
                              hexpand=True)
        w["port"] = Gtk.SpinButton.new_with_range(1, 65535, 1)
        w["port"].set_value(443)
        w["port"].set_width_chars(5)
        server = Gtk.Box(spacing=6)
        server.pack_start(w["host"], True, True, 0)
        server.pack_start(Gtk.Label(label=":"), False, False, 0)
        server.pack_start(w["port"], False, False, 0)
        self._row(grid, 0, "Nome", w["name"],
                  "Curto, sem espaço. É o que você usa em “vpnctl connect work”.")
        self._row(grid, 2, "Servidor", server)
        box.pack_start(grid, False, False, 0)

        # --- Login
        box.pack_start(self._section("Login"), False, False, 0)
        switch = Gtk.Box(homogeneous=True)
        switch.get_style_context().add_class("linked")
        w["auth_saml"] = Gtk.RadioButton.new_with_label(None, "No navegador (SAML/SSO)")
        w["auth_password"] = Gtk.RadioButton.new_with_label_from_widget(
            w["auth_saml"], "Usuário e senha")
        for rb in (w["auth_saml"], w["auth_password"]):
            rb.set_mode(False)  # aparência de botão alternado
            switch.pack_start(rb, True, True, 0)
        box.pack_start(switch, False, False, 0)
        w["auth_hint"] = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
        w["auth_hint"].get_style_context().add_class("vt-hint")
        box.pack_start(w["auth_hint"], False, False, 0)

        cred = self._grid()
        w["username"] = Gtk.Entry(activates_default=True, hexpand=True)
        w["password"] = Gtk.Entry(visibility=False, activates_default=True, hexpand=True,
                                  input_purpose=Gtk.InputPurpose.PASSWORD)
        w["password"].set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,
                                              "view-reveal-symbolic")
        w["password"].set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "Mostrar")
        w["password"].connect("icon-press", lambda e, *_: e.set_visibility(not e.get_visibility()))
        self._row(cred, 0, "Usuário", w["username"])
        self._row(cred, 1, "Senha", w["password"],
                  "Fica só em /etc/openfortivpn/<nome>.conf, legível apenas pelo root.")
        w["cred"] = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        w["cred"].add(cred)
        box.pack_start(w["cred"], False, False, 0)

        # --- Avançado
        adv = self._grid()
        w["realm"] = Gtk.Entry(placeholder_text="opcional", hexpand=True)
        w["trusted_cert"] = Gtk.Entry(placeholder_text="opcional — SHA256 do certificado",
                                      hexpand=True)
        self._row(adv, 0, "Realm", w["realm"])
        self._row(adv, 1, "Certificado", w["trusted_cert"],
                  "Pode deixar vazio: se o servidor não for confiável, o app avisa e "
                  "oferece confiar.")
        w["advanced"] = Gtk.Expander(label="Avançado")
        w["advanced"].add(adv)
        box.pack_start(w["advanced"], False, False, 4)

        # --- Opções
        w["default"] = Gtk.CheckButton(label="Usar como VPN padrão")
        w["default"].set_active(not existing)
        w["connect"] = Gtk.CheckButton(label="Conectar depois de salvar")
        box.pack_start(w["default"], False, False, 0)
        box.pack_start(w["connect"], False, False, 0)

        w["error"] = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
        box.pack_start(w["error"], False, False, 4)

        for key in ("name", "host", "username", "password", "realm", "trusted_cert"):
            w[key].connect("changed", self._validate)
        w["port"].connect("value-changed", self._validate)
        w["auth_saml"].connect("toggled", self._on_auth)
        self._on_auth()
        self.show_all()

    # -- layout helpers
    def _section(self, text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.get_style_context().add_class("vt-section")
        return lbl

    def _grid(self):
        return Gtk.Grid(row_spacing=6, column_spacing=12, margin_start=2)

    def _row(self, grid, i, label, widget, hint=None):
        lbl = Gtk.Label(label=label, xalign=1, width_chars=9)
        grid.attach(lbl, 0, i, 1, 1)
        grid.attach(widget, 1, i, 1, 1)
        if hint:
            h = Gtk.Label(label=hint, xalign=0, wrap=True, max_width_chars=48)
            h.get_style_context().add_class("vt-hint")
            grid.attach(h, 1, i + 1, 1, 1)

    # -- comportamento
    def _on_auth(self, *_):
        pw = self.widgets["auth_password"].get_active()
        self.widgets["cred"].set_reveal_child(pw)
        self.widgets["auth_hint"].set_text(
            "Usuário e senha ficam salvos para conectar sem interação."
            if pw else "Ao conectar, o navegador abre na página de login da empresa (SSO).")
        self._validate()

    def read(self):
        w = self.widgets
        data = {
            "name": w["name"].get_text().strip().lower(),
            "host": w["host"].get_text().strip(),
            "port": int(w["port"].get_value()),
            "auth": "password" if w["auth_password"].get_active() else "saml",
            "username": w["username"].get_text().strip(),
            "password": w["password"].get_text(),
            "realm": w["realm"].get_text().strip(),
            "trusted_cert": w["trusted_cert"].get_text().strip(),
        }
        return data, {"default": w["default"].get_active(),
                      "connect": w["connect"].get_active()}

    def _validate(self, *_):
        data, _f = self.read()
        err = validate_new_profile(data, self.existing)
        touched = bool(data["name"] or data["host"])
        lbl = self.widgets["error"]
        ctx = lbl.get_style_context()
        ctx.remove_class("vt-error")
        ctx.remove_class("vt-ok")
        if err and touched:
            lbl.set_text(err)
            ctx.add_class("vt-error")
        elif not err:
            lbl.set_text(f"Pronto: vpn-tray@{data['name']} · {data['host']}:{data['port']}")
            ctx.add_class("vt-ok")
        else:
            lbl.set_text("")
        self.widgets["save"].set_sensitive(err is None)
        return err

    def prefill(self, data):
        w = self.widgets
        for key in ("name", "host", "username", "password", "realm", "trusted_cert"):
            if data.get(key):
                w[key].set_text(str(data[key]))
        if data.get("port"):
            w["port"].set_value(int(data["port"]))
        (w["auth_password"] if data.get("auth") == "password" else w["auth_saml"]).set_active(True)
        if data.get("realm") or data.get("trusted_cert"):
            w["advanced"].set_expanded(True)
        self._validate()

    def import_text(self, text, filename=""):
        base = os.path.basename(filename).rsplit(".", 1)[0].lower()
        name = re.sub(r"[^a-z0-9_-]", "-", base).strip("-")[:32] if base not in ("", "config") else ""
        data, ignored = parse_openfortivpn_conf(text, name or None)
        self.prefill(data)
        if ignored:
            self.widgets["error"].set_text(
                "Importado. Ignorei (o VPN Tray não grava): " + ", ".join(ignored))
        return data, ignored

    def _on_import(self, *_):
        fc = Gtk.FileChooserNative.new("Importar configuração do openfortivpn", self,
                                       Gtk.FileChooserAction.OPEN, "Importar", "Cancelar")
        if fc.run() == Gtk.ResponseType.ACCEPT:
            path = fc.get_filename()
            try:
                with open(path) as f:
                    self.import_text(f.read(), path)
            except PermissionError:
                self.widgets["error"].set_text(
                    "Sem permissão para ler esse arquivo (é do root). Use no terminal: "
                    f"vpnctl import {path}")
            except OSError as e:
                self.widgets["error"].set_text(str(e))
        fc.destroy()


class VpnTray(Gtk.Application):
    def __init__(self, backend=None, app_id=APP_ID, settings_path=CFG_FILE,
                 poll_seconds=2, notify=True):
        super().__init__(application_id=app_id)
        self.backend = backend or Backend()
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.poll_seconds = poll_seconds
        self.use_notify = notify
        self.profiles, self.props = {}, {}
        self.sessions, self.finished = {}, {}
        self.started_by_us = set()
        self.policy = {"require_password_connect": False}
        self.state = OFF
        self.tooltip = ""
        self.icon_path = None
        self.spec = None
        self.menu = None
        self.status = None
        self.indicator = None
        self.log_windows = {}
        self.notifications = []  # (título, corpo) — útil nos testes
        self._autoconnected = False
        self._first_poll_done = False

    # ---------------------------------------------------------------- setup
    def do_startup(self):
        Gtk.Application.do_startup(self)
        if self.use_notify:
            Notify.init("VPN Tray")
        self.hold()
        self.setup_ui()

    def setup_ui(self):
        """Ícone + menu + polling. Separado do do_startup para os testes."""
        if XApp is not None:
            self.status = XApp.StatusIcon()
            self.status.set_name("vpn-tray")
        else:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AI
            self.indicator = AI.Indicator.new(
                "vpn-tray", icon(OFF), AI.IndicatorCategory.SYSTEM_SERVICES)
            self.indicator.set_status(AI.IndicatorStatus.ACTIVE)
        self.poll()
        if self.poll_seconds:
            GLib.timeout_add_seconds(self.poll_seconds, self.poll)

    def do_activate(self):
        pass

    # --------------------------------------------------------------- estado
    def poll(self):
        self.profiles = self.backend.profiles()
        self.props = self.backend.unit_props(list(self.profiles))
        self.policy = self.backend.policy()
        for name, p in self.props.items():
            st = p.get("ActiveState")
            active = st in ("active", "activating", "deactivating")
            inv = p.get("InvocationID", "")
            sess = self.sessions.get(name)
            if active and inv and (sess is None or sess.invocation != inv):
                if sess:
                    sess.close()
                # "Ao vivo" = começou depois que o app abriu (pelo menu, pela
                # CLI ou por um agente): aí abre o navegador e notifica.
                # Execuções que já estavam no ar ao abrir o app só são relidas.
                live = name in self.started_by_us or self._first_poll_done
                self.started_by_us.discard(name)
                sess = Session(name, inv, live, self._on_session_event)
                self.sessions[name] = sess
                self.finished.pop(name, None)
                sess.handle = self.backend.follow_invocation(inv, sess.feed)
            elif not active and sess is not None:
                sess.close()
                del self.sessions[name]
                self.finished[name] = sess
                if st == "failed":
                    self.notify(f"VPN {name}: falhou", sess.last_error or "Veja o log no menu.")
                elif sess.tunnel_up:
                    self.notify(f"VPN {name}", "Desconectada.")
        for gone in set(self.sessions) - set(self.profiles):
            self.sessions.pop(gone).close()
        self._first_poll_done = True
        if not self._autoconnected:
            self._autoconnected = True
            d = self.default()
            if self.settings.get("autoconnect") and d and self.state_of(d) == OFF:
                self.connect_profile(d)
        self.refresh()
        return True

    def _on_session_event(self, kind, sess):
        if kind == "auth":
            self.open_url(sess.auth_url)
            self.notify(f"VPN {sess.name}", "Faça o login no navegador que abriu.")
        elif kind == "cert":
            self.notify(f"VPN {sess.name}: certificado não confiável",
                        "Use “Confiar no certificado” no menu, se o servidor for o esperado.")
        elif kind == "up":
            self.notify(f"VPN {sess.name}", "Conectada.")
        self.refresh()

    def state_of(self, name):
        sess = self.sessions.get(name)
        st = self.props.get(name, {}).get("ActiveState", "inactive")
        return profile_state(st, bool(sess and sess.tunnel_up))

    def default(self):
        d = self.settings.get("default")
        return d if d in self.profiles else next(iter(self.profiles), None)

    def refresh(self):
        states = {n: self.state_of(n) for n in self.profiles}
        external = (not any(s in (ON, CONNECTING) for s in states.values())
                    and self.backend.external_running())
        overall = overall_state(states, external)
        connecting = first_with(states, CONNECTING)
        sess = self.sessions.get(connecting) if connecting else None
        waiting = bool(sess and sess.auth_url and not sess.tunnel_up)
        default = self.default()
        self.tooltip = tooltip_for(overall, states, default, waiting, external)
        info = {}
        for n in self.profiles:
            s = self.sessions.get(n) or self.finished.get(n)
            if s:
                info[n] = s.info()
        agents = self.settings.get("agents", {})
        security = {"require_password": self.policy.get("require_password_connect"),
                    "agents_connect": agents.get("allow_connect"),
                    "agents_disconnect": agents.get("allow_disconnect")}
        spec = menu_spec(list(self.profiles), states, default, info, external,
                         self.settings.get("autoconnect"), security)

        path = icon(overall)
        if self.status:
            if path != self.icon_path:
                self.status.set_icon_name(path)
            self.status.set_tooltip_text(self.tooltip)
        elif self.indicator:
            self.indicator.set_icon_full(path, self.tooltip)
        self.icon_path = path
        self.state = overall

        # Só recria o menu se mudou — recriar a cada 2 s fechava o menu aberto.
        if spec != self.spec:
            self.spec = spec
            if self.status or self.indicator:
                self.menu = self.build_gtk_menu(spec)
                if self.status:
                    self.status.set_primary_menu(self.menu)    # clique esquerdo
                    self.status.set_secondary_menu(self.menu)  # clique direito
                else:
                    self.indicator.set_menu(self.menu)

    def force_menu_rebuild(self):
        """Depois de uma ação cancelada, o check do menu precisa voltar ao real."""
        self.spec = None
        self.refresh()

    # ----------------------------------------------------------------- menu
    def build_gtk_menu(self, spec):
        menu = Gtk.Menu()
        for entry in spec:
            kind = entry[0]
            if kind == "sep":
                menu.append(Gtk.SeparatorMenuItem())
            elif kind == "label":
                mi = Gtk.MenuItem(label=entry[1])
                mi.set_sensitive(False)
                menu.append(mi)
            elif kind == "item":
                mi = Gtk.MenuItem(label=entry[1])
                mi.connect("activate", self._dispatch, entry[2])
                menu.append(mi)
            elif kind == "check":
                mi = Gtk.CheckMenuItem(label=entry[1])
                mi.set_active(entry[2])
                mi.connect("toggled", self._dispatch, entry[3])
                menu.append(mi)
            elif kind == "submenu":
                mi = Gtk.MenuItem(label=entry[1])
                mi.set_submenu(self.build_gtk_menu(entry[2]))
                menu.append(mi)
            elif kind == "radio":
                mi = Gtk.MenuItem(label=entry[1])
                sub, group = Gtk.Menu(), None
                for label, active, action in entry[2]:
                    r = Gtk.RadioMenuItem.new_with_label_from_widget(group, label)
                    group = group or r
                    r.set_active(active)
                    r.connect("toggled", lambda w, a=action: w.get_active() and self.run_action(a))
                    sub.append(r)
                mi.set_submenu(sub)
                menu.append(mi)
        menu.show_all()
        return menu

    def _dispatch(self, _widget, action):
        self.run_action(action)

    def run_action(self, action):
        verb, *args = action
        handlers = {
            "connect": self.connect_profile,
            "disconnect": self.disconnect_profile,
            "open_url": self.open_url,
            "trust_cert": self.trust_cert,
            "add": self.add_dialog,
            "log": self.show_log,
            "set_default": self.set_default,
            "toggle_autoconnect": self.toggle_autoconnect,
            "toggle_require_password": self.toggle_require_password,
            "toggle_agents": self.toggle_agents,
            "remove": self.remove_profile,
            "quit": self.quit,
        }
        handlers[verb](*args)

    # ---------------------------------------------------------------- ações
    def _after_systemctl(self, verb, name):
        def cb(code, err):
            if code != 0:
                msg = err[:200] or "veja o log"
                if "authentication" in msg.lower() or "autentica" in msg.lower():
                    msg = "Senha não confirmada (política “pedir senha ao conectar”)."
                self.notify(f"VPN {name}: não consegui {verb}", msg)
            self.poll()
        return cb

    def connect_profile(self, name):
        for other in self.profiles:
            if other != name and self.state_of(other) in (ON, CONNECTING):
                self.backend.systemctl("stop", other, self._after_systemctl("stop", other))
        self.finished.pop(name, None)
        self.started_by_us.add(name)
        self.backend.systemctl("start", name, self._after_systemctl("start", name))

    def disconnect_profile(self, name):
        self.backend.systemctl("stop", name, self._after_systemctl("stop", name))

    def _save(self):
        save_settings(self.settings, self.settings_path)

    def set_default(self, name):
        self.settings["default"] = name
        self._save()
        self.refresh()

    def toggle_autoconnect(self):
        self.settings["autoconnect"] = not self.settings.get("autoconnect")
        self._save()
        self.refresh()

    def toggle_agents(self, key):
        agents = self.settings.setdefault("agents", {})
        agents[key] = not agents.get(key)
        self._save()
        self.refresh()

    def toggle_require_password(self):
        new = "off" if self.policy.get("require_password_connect") else "on"
        # Mudar a política sempre pede senha de admin (pkexec) — nos dois
        # sentidos, para um agente não conseguir desligar a trava sozinho.
        self._helper(["policy", "require-password", new], on_ok=lambda: self.notify(
            "VPN Tray", "Conectar agora pede senha." if new == "on"
            else "Conectar não pede mais senha."))

    def open_url(self, url):
        try:
            self.backend.open_url(url)
        except GLib.Error as e:
            self.notify("Não consegui abrir o navegador", f"{e.message}\n{url}")

    def show_log(self, name):
        win = self.log_windows.get(name)
        if win is None:
            win = LogWindow(self.backend, name)
            win.connect("destroy", lambda *_: self.log_windows.pop(name, None))
            self.log_windows[name] = win
            if self.get_is_registered():
                self.add_window(win)
        win.show_all()
        win.present()
        return win

    def _helper(self, args, stdin_text=None, on_ok=None):
        def cb(code, err):
            if code == 0:
                on_ok and on_ok()
            elif code not in (126, 127):  # 126/127 = senha cancelada no pkexec
                self.error_dialog(err or "falhou")
            self.poll()
            self.force_menu_rebuild()
        self.backend.helper(args, stdin_text, cb)

    def confirm(self, text, secondary, kind=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO):
        dlg = Gtk.MessageDialog(message_type=kind, buttons=buttons, text=text)
        dlg.format_secondary_text(secondary)
        resp = dlg.run()
        dlg.destroy()
        return resp in (Gtk.ResponseType.YES, Gtk.ResponseType.OK)

    def trust_cert(self, name, digest):
        if self.confirm(f"Confiar no certificado do servidor de “{name}”?",
                        f"SHA256: {digest}\n\nSó confirme se você esperava esse servidor "
                        "(ex.: compare com o hash que o time de infra passou)."):
            def after():
                self.finished.pop(name, None)
                self.connect_profile(name)
            self._helper(["trust", name, digest], on_ok=after)

    def remove_profile(self, name):
        if self.confirm(f"Remover a VPN “{name}”?",
                        f"Apaga {CONF_DIR}/{name}.conf e .args (pede sua senha). "
                        "Não dá para desfazer.",
                        Gtk.MessageType.WARNING, Gtk.ButtonsType.OK_CANCEL):
            def after():
                if self.settings.get("default") == name:
                    self.settings["default"] = None
                    self._save()
            self._helper(["remove", name], on_ok=after)

    def error_dialog(self, msg):
        dlg = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.CLOSE, text="VPN Tray")
        dlg.format_secondary_text(msg)
        dlg.run()
        dlg.destroy()

    def notify(self, title, body=""):
        self.notifications.append((title, body))
        if not self.use_notify:
            return
        try:
            Notify.Notification.new(title, body, icon(self.state)).show()
        except GLib.Error:
            pass

    # ------------------------------------------------------ adicionar VPN
    def build_add_dialog(self):
        return AddVpnDialog(self.profiles)

    def add_dialog(self):
        dlg = self.build_add_dialog()
        resp = dlg.run()
        data, flags = dlg.read()
        err = dlg._validate()
        dlg.destroy()
        if resp == Gtk.ResponseType.OK and not err:
            self.save_new_profile(data, flags)

    def save_new_profile(self, data, flags):
        if isinstance(flags, bool):  # compat: save_new_profile(data, want_default)
            flags = {"default": flags, "connect": False}

        def after():
            if flags.get("default"):
                self.settings["default"] = data["name"]
                self._save()
            self.notify(f"VPN {data['name']} adicionada",
                        "Conectando…" if flags.get("connect") else "Conecte pelo menu do ícone.")
            if flags.get("connect"):
                self.profiles = self.backend.profiles()
                self.connect_profile(data["name"])
        self._helper(["add"], stdin_text=json.dumps(data), on_ok=after)


def main(argv):
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if "--demo" in argv:
        # Tudo de mentira: dá para clicar em tudo sem tocar na VPN real.
        argv = [a for a in argv if a != "--demo"]
        fake = FakeBackend({"work": {"VPN_AUTH": "saml"}, "teste": {"VPN_AUTH": "saml"},
                            "quebrada": {"VPN_AUTH": "saml"}})
        fake.open_url = lambda url: print("[demo] abriria o navegador em", url)
        GLib.timeout_add(1500, fake.tick)
        demo_cfg = os.path.join(GLib.get_user_cache_dir(), "vpn-tray-demo.json")
        app = VpnTray(backend=fake, app_id=APP_ID + ".demo", settings_path=demo_cfg,
                      poll_seconds=1)
    else:
        app = VpnTray()
    return app.run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
