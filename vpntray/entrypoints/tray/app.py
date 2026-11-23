"""Ícone na bandeja: liga o ConnectionMonitor e os casos de uso ao GTK.

Qualquer clique (esquerdo ou direito) abre o menu; conectar e desconectar
são sempre itens do menu, nunca o clique direto no ícone.
"""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import GLib, Gtk, Notify  # noqa: E402

try:
    gi.require_version("XApp", "1.0")
    from gi.repository import XApp
except (ValueError, ImportError):
    XApp = None

from ...adapters.desktop import TRAY_DBUS_NAME  # noqa: E402
from ...application.errors import AdminCancelled, AuthenticationDenied, VpnTrayError  # noqa: E402
from ...application.monitor import ConnectionMonitor  # noqa: E402
from ...composition import Container  # noqa: E402
from ...domain.model import State  # noqa: E402
from .add_dialog import AddVpnDialog  # noqa: E402
from .gtk_io import thread_runner  # noqa: E402
from .log_window import LogWindow  # noqa: E402
from .presenter import menu_spec, tooltip_for  # noqa: E402

ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))), "icons"
)


def icon(state: State) -> str:
    return os.path.join(ICON_DIR, f"vpn-{state.value}.svg")


class VpnTrayApp(Gtk.Application):
    def __init__(
        self,
        container: Container,
        follower,
        *,
        app_id: str = TRAY_DBUS_NAME,
        poll_seconds: int = 2,
        notify: bool = True,
        runner=thread_runner,
    ):
        super().__init__(application_id=app_id)
        self.c = container
        self.follower = follower
        self.poll_seconds = poll_seconds
        self.use_notify = notify
        self.run_task = runner
        self.monitor = ConnectionMonitor(
            container.profiles_repo,
            container.services,
            container.policy,
            container.probe,
            follower,
            self._on_monitor_event,
        )
        self.state = State.OFF
        self.tooltip = ""
        self.icon_path: str | None = None
        self.spec: list | None = None
        self.menu: Gtk.Menu | None = None
        self.status = None
        self.indicator = None
        self.log_windows: dict[str, LogWindow] = {}
        self.notifications: list[tuple[str, str]] = []
        self._autoconnected = False

    # ---------------------------------------------------------------- setup
    def do_startup(self):
        Gtk.Application.do_startup(self)
        if self.use_notify:
            Notify.init("VPN Tray")
        self.hold()
        self.setup_ui()

    def setup_ui(self) -> None:
        """Ícone + menu + polling (separado do do_startup para os testes)."""
        if XApp is not None:
            self.status = XApp.StatusIcon()
            self.status.set_name("vpn-tray")
        else:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AI

            self.indicator = AI.Indicator.new(
                "vpn-tray", icon(State.OFF), AI.IndicatorCategory.SYSTEM_SERVICES
            )
            self.indicator.set_status(AI.IndicatorStatus.ACTIVE)
        self.poll()
        if self.poll_seconds:
            GLib.timeout_add_seconds(self.poll_seconds, self.poll)

    def do_activate(self):
        pass

    # --------------------------------------------------------------- estado
    def poll(self) -> bool:
        self.monitor.poll()
        if not self._autoconnected:
            self._autoconnected = True
            settings = self.c.settings.load()
            d = self.default()
            if settings.autoconnect and d and self.monitor.state_of(d) == State.OFF:
                self.connect_profile(d)
        return True

    def _on_monitor_event(self, kind: str, profile: str, data) -> None:
        if kind == "auth":
            self.open_url(data)
            self.notify(f"VPN {profile}", "Faça o login no navegador que abriu.")
        elif kind == "cert":
            self.notify(
                f"VPN {profile}: certificado não confiável",
                "Use “Confiar no certificado” no menu, se o servidor for o esperado.",
            )
        elif kind == "up":
            self.notify(f"VPN {profile}", "Conectada.")
        elif kind == "failed":
            self.notify(f"VPN {profile}: falhou", data or "Veja o log no menu.")
        elif kind == "down":
            self.notify(f"VPN {profile}", "Desconectada.")
        self.refresh()

    def default(self) -> str | None:
        d = self.c.settings.load().default
        profiles = self.monitor.profiles
        return d if d in profiles else next(iter(profiles), None)

    def refresh(self) -> None:
        m = self.monitor
        states = m.states()
        external = m.external(states)
        overall = m.overall()
        settings = self.c.settings.load()
        self.tooltip = tooltip_for(overall, states, self.default(), m.waiting_login(), external)
        info = {n: m.info(n) for n in m.profiles if m.info(n)}
        security = {
            "require_password": m.policy.require_password_connect,
            "agents_connect": settings.agents.allow_connect,
            "agents_disconnect": settings.agents.allow_disconnect,
        }
        spec = menu_spec(
            list(m.profiles), states, self.default(), info, external, settings.autoconnect, security
        )
        path = icon(overall)
        if self.status:
            if path != self.icon_path:
                self.status.set_icon_name(path)
            self.status.set_tooltip_text(self.tooltip)
        elif self.indicator:
            self.indicator.set_icon_full(path, self.tooltip)
        self.icon_path, self.state = path, overall
        # Só recria o menu se mudou — recriar a cada 2 s fechava o menu aberto.
        if spec != self.spec:
            self.spec = spec
            if self.status or self.indicator:
                self.menu = self.build_gtk_menu(spec)
                if self.status:
                    self.status.set_primary_menu(self.menu)  # clique esquerdo
                    self.status.set_secondary_menu(self.menu)  # clique direito
                else:
                    self.indicator.set_menu(self.menu)

    def force_menu_rebuild(self) -> None:
        """Depois de uma ação cancelada, os checks do menu voltam ao estado real."""
        self.spec = None
        self.refresh()

    # ----------------------------------------------------------------- menu
    def build_gtk_menu(self, spec: list) -> Gtk.Menu:
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
                mi.connect("activate", lambda _w, a=entry[2]: self.run_action(a))
                menu.append(mi)
            elif kind == "check":
                mi = Gtk.CheckMenuItem(label=entry[1])
                mi.set_active(entry[2])
                mi.connect("toggled", lambda _w, a=entry[3]: self.run_action(a))
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

    def run_action(self, action: tuple) -> None:
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
    def _task(self, fn, *, title: str, on_ok=None) -> None:
        """Roda uma ação que pode bloquear (senha) e trata o resultado na UI."""

        def done(_result, error):
            if error is None:
                if on_ok:
                    on_ok()
            elif isinstance(error, AdminCancelled):
                pass
            elif isinstance(error, AuthenticationDenied):
                self.notify(title, str(error))
            elif isinstance(error, VpnTrayError):
                self.error_dialog(str(error))
            else:
                self.notify(title, f"{type(error).__name__}: {error}")
            self.poll()
            self.force_menu_rebuild()

        self.run_task(fn, done)

    def connect_profile(self, name: str) -> None:
        self._task(lambda: self.monitor.connect(name), title=f"VPN {name}: não conectou")

    def disconnect_profile(self, name: str) -> None:
        self._task(lambda: self.monitor.disconnect(name), title=f"VPN {name}: não desconectou")

    def set_default(self, name: str) -> None:
        self.c.preferences.set_default(name)
        self.refresh()

    def toggle_autoconnect(self) -> None:
        self.c.preferences.set_autoconnect(not self.c.settings.load().autoconnect)
        self.refresh()

    def toggle_agents(self, key: str) -> None:
        current = getattr(self.c.settings.load().agents, key)
        self.c.preferences.set_agent_permission(key, not current)
        self.refresh()

    def toggle_require_password(self) -> None:
        new = not self.monitor.policy.require_password_connect
        # Mudar a política pede senha de admin nos dois sentidos: um agente não
        # consegue desligar a trava sozinho.
        self._task(
            lambda: self.c.preferences.set_require_password(new),
            title="Política",
            on_ok=lambda: self.notify(
                "VPN Tray", "Conectar agora pede senha." if new else "Conectar não pede mais senha."
            ),
        )

    def open_url(self, url: str) -> None:
        try:
            self.c.browser.open(url)
        except Exception as e:  # noqa: BLE001
            self.notify("Não consegui abrir o navegador", f"{e}\n{url}")

    def show_log(self, name: str) -> LogWindow:
        win = self.log_windows.get(name)
        if win is None:
            win = LogWindow(self.follower, name, icon(State.ON))
            win.connect("destroy", lambda *_: self.log_windows.pop(name, None))
            self.log_windows[name] = win
            if self.get_is_registered():
                self.add_window(win)
        win.show_all()
        win.present()
        return win

    def confirm(
        self, text: str, secondary: str, kind=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO
    ) -> bool:
        dlg = Gtk.MessageDialog(message_type=kind, buttons=buttons, text=text)
        dlg.format_secondary_text(secondary)
        resp = dlg.run()
        dlg.destroy()
        return resp in (Gtk.ResponseType.YES, Gtk.ResponseType.OK)

    def trust_cert(self, name: str, digest: str) -> None:
        if self.confirm(
            f"Confiar no certificado do servidor de “{name}”?",
            f"SHA256: {digest}\n\nSó confirme se você esperava esse servidor "
            "(ex.: compare com o hash que o time de infra passou).",
        ):
            self._task(
                lambda: self.c.profiles.trust(name, digest),
                title="Certificado",
                on_ok=lambda: self.connect_profile(name),
            )

    def remove_profile(self, name: str) -> None:
        if self.confirm(
            f"Remover a VPN “{name}”?",
            f"Apaga /etc/openfortivpn/{name}.conf e .args (pede sua senha). Não dá para desfazer.",
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK_CANCEL,
        ):
            self._task(lambda: self.c.profiles.remove(name), title="Remover VPN")

    def error_dialog(self, msg: str) -> None:
        dlg = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE, text="VPN Tray"
        )
        dlg.format_secondary_text(msg)
        dlg.run()
        dlg.destroy()

    def notify(self, title: str, body: str = "") -> None:
        self.notifications.append((title, body))
        if not self.use_notify:
            return
        try:
            Notify.Notification.new(title, body, icon(self.state)).show()
        except GLib.Error:
            # Sem servidor de notificações: o aviso fica só em self.notifications.
            return

    # ------------------------------------------------------ adicionar VPN
    def build_add_dialog(self) -> AddVpnDialog:
        return AddVpnDialog(
            self.c.profiles.validate,
            lambda text, filename: self.c.profiles.parse_import(text, filename),
            existing_count=len(self.monitor.profiles),
        )

    def add_dialog(self) -> None:
        dlg = self.build_add_dialog()
        resp = dlg.run()
        profile, flags = dlg.read()
        err = dlg._validate()
        dlg.destroy()
        if resp == Gtk.ResponseType.OK and not err:
            self.save_new_profile(profile, flags)

    def save_new_profile(self, profile, flags: dict) -> None:
        def after():
            self.notify(
                f"VPN {profile.name} adicionada",
                "Conectando…" if flags.get("connect") else "Conecte pelo menu do ícone.",
            )
            if flags.get("connect"):
                self.monitor.poll()
                self.connect_profile(profile.name)

        self._task(
            lambda: self.c.profiles.add(profile, make_default=bool(flags.get("default"))),
            title="Nova VPN",
            on_ok=after,
        )


def main(argv: list[str]) -> int:
    import signal

    from ...composition import build, build_memory
    from .gtk_io import JournalctlFollower, inline_runner

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if "--demo" in argv:
        # Tudo de mentira: dá para clicar em tudo sem tocar na VPN real.
        from ...adapters.memory import MemorySystem

        argv = [a for a in argv if a != "--demo"]
        system = MemorySystem({"work": "saml", "lab": "saml", "quebrada": "saml"})
        system.open = lambda url: print("[demo] abriria o navegador em", url)
        GLib.timeout_add(1500, system.tick)
        app = VpnTrayApp(
            build_memory(system),
            system,
            app_id=TRAY_DBUS_NAME + ".demo",
            poll_seconds=1,
            runner=inline_runner,
        )
    else:
        app = VpnTrayApp(build(), JournalctlFollower())
    return app.run(argv)
