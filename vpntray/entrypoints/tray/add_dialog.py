"""Formulário "Nova VPN": seções, login como alternância, avançado recolhido,
validação ao vivo e importação de .conf do openfortivpn."""

from __future__ import annotations

from gi.repository import Gtk

from ...domain.model import NewProfile

CSS = b"""
.vt-section { font-weight: bold; opacity: 0.75; margin-top: 6px; }
.vt-hint { opacity: 0.6; font-size: 90%; }
.vt-error { color: #d0453a; }
.vt-ok { color: #2f9e57; }
"""


class AddVpnDialog(Gtk.Dialog):
    """Formulário de nova VPN: seções, login como alternância, avançado
    recolhido, validação ao vivo e importação de .conf do openfortivpn."""

    def __init__(self, validate, parse_import, existing_count: int = 0, parent=None):
        super().__init__(title="Nova VPN", use_header_bar=True, modal=True, transient_for=parent)
        self._validate_profile = validate  # NewProfile -> str | None
        self._parse_import = parse_import  # (texto, arquivo) -> (NewProfile, ignoradas)
        self.set_default_size(480, -1)
        self.set_resizable(False)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        hb = self.get_header_bar()
        hb.set_subtitle("openfortivpn")
        self.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        save = self.add_button("Salvar", Gtk.ResponseType.OK)
        save.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)

        w = self.widgets = {"save": save}
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=22,
            margin_end=22,
            margin_top=14,
            margin_bottom=18,
        )
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
        w["host"] = Gtk.Entry(placeholder_text="vpn.example.com", activates_default=True, hexpand=True)
        w["port"] = Gtk.SpinButton.new_with_range(1, 65535, 1)
        w["port"].set_value(443)
        w["port"].set_width_chars(5)
        server = Gtk.Box(spacing=6)
        server.pack_start(w["host"], True, True, 0)
        server.pack_start(Gtk.Label(label=":"), False, False, 0)
        server.pack_start(w["port"], False, False, 0)
        self._row(grid, 0, "Nome", w["name"], "Curto, sem espaço. É o que você usa em “vpnctl connect work”.")
        self._row(grid, 2, "Servidor", server)
        box.pack_start(grid, False, False, 0)

        # --- Login
        box.pack_start(self._section("Login"), False, False, 0)
        switch = Gtk.Box(homogeneous=True)
        switch.get_style_context().add_class("linked")
        w["auth_saml"] = Gtk.RadioButton.new_with_label(None, "No navegador (SAML/SSO)")
        w["auth_password"] = Gtk.RadioButton.new_with_label_from_widget(w["auth_saml"], "Usuário e senha")
        for rb in (w["auth_saml"], w["auth_password"]):
            rb.set_mode(False)  # aparência de botão alternado
            switch.pack_start(rb, True, True, 0)
        box.pack_start(switch, False, False, 0)
        w["auth_hint"] = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
        w["auth_hint"].get_style_context().add_class("vt-hint")
        box.pack_start(w["auth_hint"], False, False, 0)

        cred = self._grid()
        w["username"] = Gtk.Entry(activates_default=True, hexpand=True)
        w["password"] = Gtk.Entry(
            visibility=False, activates_default=True, hexpand=True, input_purpose=Gtk.InputPurpose.PASSWORD
        )
        w["password"].set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-reveal-symbolic")
        w["password"].set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "Mostrar")
        w["password"].connect("icon-press", lambda e, *_: e.set_visibility(not e.get_visibility()))
        self._row(cred, 0, "Usuário", w["username"])
        self._row(
            cred,
            1,
            "Senha",
            w["password"],
            "Fica só em /etc/openfortivpn/<nome>.conf, legível apenas pelo root.",
        )
        w["cred"] = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        w["cred"].add(cred)
        box.pack_start(w["cred"], False, False, 0)

        # --- Avançado
        adv = self._grid()
        w["realm"] = Gtk.Entry(placeholder_text="opcional", hexpand=True)
        w["trusted_cert"] = Gtk.Entry(placeholder_text="opcional — SHA256 do certificado", hexpand=True)
        self._row(adv, 0, "Realm", w["realm"])
        self._row(
            adv,
            1,
            "Certificado",
            w["trusted_cert"],
            "Pode deixar vazio: se o servidor não for confiável, o app avisa e oferece confiar.",
        )
        w["advanced"] = Gtk.Expander(label="Avançado")
        w["advanced"].add(adv)
        box.pack_start(w["advanced"], False, False, 4)

        # --- Opções
        w["default"] = Gtk.CheckButton(label="Usar como VPN padrão")
        w["default"].set_active(existing_count == 0)
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
            if pw
            else "Ao conectar, o navegador abre na página de login da empresa (SSO)."
        )
        self._validate()

    def read(self) -> tuple[NewProfile, dict]:
        w = self.widgets
        profile = NewProfile(
            name=w["name"].get_text().strip().lower(),
            host=w["host"].get_text().strip(),
            port=int(w["port"].get_value()),
            auth="password" if w["auth_password"].get_active() else "saml",
            username=w["username"].get_text().strip(),
            password=w["password"].get_text(),
            realm=w["realm"].get_text().strip(),
            trusted_cert=w["trusted_cert"].get_text().strip(),
        )
        return profile, {"default": w["default"].get_active(), "connect": w["connect"].get_active()}

    def _validate(self, *_):
        data, _f = self.read()
        err = self._validate_profile(data)
        touched = bool(data.name or data.host)
        lbl = self.widgets["error"]
        ctx = lbl.get_style_context()
        ctx.remove_class("vt-error")
        ctx.remove_class("vt-ok")
        if err and touched:
            lbl.set_text(err)
            ctx.add_class("vt-error")
        elif not err:
            lbl.set_text(f"Pronto: vpn-tray@{data.name} · {data.host}:{data.port}")
            ctx.add_class("vt-ok")
        else:
            lbl.set_text("")
        self.widgets["save"].set_sensitive(err is None)
        return err

    def prefill(self, p: NewProfile) -> None:
        w = self.widgets
        for key in ("name", "host", "username", "password", "realm", "trusted_cert"):
            value = getattr(p, key)
            if value:
                w[key].set_text(str(value))
        if p.port:
            w["port"].set_value(int(p.port))
        (w["auth_password"] if p.auth == "password" else w["auth_saml"]).set_active(True)
        if p.realm or p.trusted_cert:
            w["advanced"].set_expanded(True)
        self._validate()

    def import_text(self, text: str, filename: str = "") -> tuple[NewProfile, list[str]]:
        profile, ignored = self._parse_import(text, filename)
        self.prefill(profile)
        if ignored:
            self.widgets["error"].set_text("Importado. Ignorei (o VPN Tray não grava): " + ", ".join(ignored))
        return profile, ignored

    def _on_import(self, *_):
        fc = Gtk.FileChooserNative.new(
            "Importar configuração do openfortivpn", self, Gtk.FileChooserAction.OPEN, "Importar", "Cancelar"
        )
        if fc.run() == Gtk.ResponseType.ACCEPT:
            path = fc.get_filename()
            try:
                with open(path) as f:
                    self.import_text(f.read(), path)
            except PermissionError:
                self.widgets["error"].set_text(
                    f"Sem permissão para ler esse arquivo (é do root). Use no terminal: vpnctl import {path}"
                )
            except OSError as e:
                self.widgets["error"].set_text(str(e))
        fc.destroy()
