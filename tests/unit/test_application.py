"""Casos de uso com o sistema em memória (sem systemd, sem tela)."""

import pytest

from vpntray.application.errors import (
    AuthenticationDenied,
    ConfirmationRequired,
    InvalidProfile,
    NotFound,
    PermissionDenied,
)
from vpntray.application.monitor import ConnectionMonitor
from vpntray.domain.model import NewProfile, State


# ------------------------------------------------------------------ status
def test_status_inicial(container):
    st = container.status.get()
    assert st["overall"] == "off" and st["default"] == "work"
    assert st["profiles"]["work"]["label"] == "desconectada"
    assert st["profiles"]["work"]["unit"] == "vpn-tray@work.service"


def test_status_aguardando_login(container, system):
    system.start("work")
    system.tick(), system.tick()
    p = container.status.get()["profiles"]["work"]
    assert p["state"] == "connecting" and p["waiting_browser_login"]
    assert p["login_url"] == "https://vpn.work.example/remote/saml/start?redirect=1"


def test_status_vpn_fora_do_app(container, system):
    system.external = True
    st = container.status.get()
    assert st["overall"] == "on" and st["external_openfortivpn"]


# -------------------------------------------------------------- conexão
def test_connect_espera_subir_e_abre_navegador_sem_icone(container, system):
    urls = []
    res = container.connection.connect("work", wait=30, on_login_url=urls.append)
    assert res["state"] == "on" and res["profile"] == "work"
    assert system.opened == ["https://vpn.work.example/remote/saml/start?redirect=1"]
    assert urls == system.opened, "URL anunciada uma vez só"


def test_connect_com_icone_aberto_nao_abre_navegador(container, system):
    system.tray = True
    container.connection.connect("work", wait=30)
    assert system.opened == [], "quem abre é o ícone"


def test_connect_ja_conectada(container, system):
    container.connection.connect("work", wait=30)
    assert container.connection.connect("work")["already"] is True


def test_connect_derruba_a_outra(container, system):
    container.connection.connect("work", wait=30)
    container.connection.connect("quebrada", wait=30)
    assert ("stop", "work") in system.calls


def test_connect_falha_de_certificado(container, system):
    res = container.connection.connect("quebrada", wait=30)
    assert res["state"] == "error"
    assert res["untrusted_cert"] == "ab" * 32


def test_connect_senha_recusada(container, system):
    system.deny_auth = True
    with pytest.raises(AuthenticationDenied):
        container.connection.connect("work")


def test_connect_sem_esperar(container):
    assert container.connection.connect("work", wait=0)["started"] is True


def test_disconnect_a_ativa(container, system):
    container.connection.connect("work", wait=30)
    assert container.connection.disconnect() == "work"
    with pytest.raises(NotFound, match="Nenhuma VPN ativa"):
        container.connection.disconnect()


# ---------------------------------------------------------------- perfis
def test_add_valida_e_define_padrao(container, system):
    container.profiles.add(NewProfile("nova", "vpn.example.org"), make_default=True)
    assert "nova" in system.list()
    assert container.settings.load().default == "nova"
    with pytest.raises(InvalidProfile, match="Já existe"):
        container.profiles.add(NewProfile("nova", "vpn.example.org"))


def test_parse_import_tira_nome_do_arquivo(container):
    p, ignored = container.profiles.parse_import(
        "host = vpn.example.com\nset-dns = 0\n", "/tmp/Empresa X.conf"
    )
    assert p.name == "empresa-x" and ignored == ["set-dns"]
    p, _ = container.profiles.parse_import("host = h.example\n", "/etc/openfortivpn/config")
    assert p.name == "", "o 'config' padrão do pacote não vira nome"


def test_remove_limpa_padrao(container, system):
    container.preferences.set_default("work")
    container.profiles.remove("work")
    assert "work" not in system.list() and container.settings.load().default is None


def test_trust_normaliza_e_valida(container, system):
    container.profiles.trust("work", "AB:" * 31 + "AB")
    assert system.calls[-1] == ("admin", "trust", "work", "ab" * 32)
    with pytest.raises(InvalidProfile):
        container.profiles.trust("work", "nope")


# ----------------------------------------------------------- preferências
def test_preferencias(container, system):
    container.preferences.set_autoconnect(True)
    container.preferences.set_agent_permission("allow_connect", False)
    s = container.settings.load()
    assert s.autoconnect and not s.agents.allow_connect
    container.preferences.set_require_password(True)
    assert system.policy_data.require_password_connect
    with pytest.raises(KeyError):
        container.preferences.set_agent_permission("root", True)


# ------------------------------------------------------------ guarda (MCP)
def test_guard(container):
    g = container.guard
    with pytest.raises(ConfirmationRequired):
        g.check("connect", False)
    g.check("connect", True)
    container.preferences.set_agent_permission("allow_disconnect", False)
    with pytest.raises(PermissionDenied, match="desconectem"):
        g.check("disconnect", True)
    container.preferences.set_agent_permission("enabled", False)
    with pytest.raises(PermissionDenied, match="desligados"):
        g.require_enabled()


# ---------------------------------------------------------------- monitor
@pytest.fixture
def monitor(system):
    events = []
    m = ConnectionMonitor(
        system, system, system.policy_reader, system, system, lambda k, p, d: events.append((k, p, d))
    )
    m.events = events
    m.poll()
    return m


def advance(system, monitor, cond, steps=10):
    for _ in range(steps):
        if cond():
            return True
        system.tick()
        monitor.poll()
    return cond()


def test_monitor_fluxo_saml(system, monitor):
    monitor.connect("work")
    monitor.poll()
    assert monitor.state_of("work") == State.CONNECTING
    assert advance(system, monitor, lambda: monitor.state_of("work") == State.ON)
    kinds = [e[0] for e in monitor.events if e[0] != "changed"]
    assert kinds == ["auth", "up"]
    assert monitor.events[[e[0] for e in monitor.events].index("auth")][2].startswith("https://")


def test_monitor_conexao_iniciada_fora_tambem_e_ao_vivo(system, monitor):
    """CLI/agente deu start: o ícone abre o login mesmo assim."""
    system.start("work")
    monitor.poll()
    assert advance(system, monitor, lambda: any(e[0] == "auth" for e in monitor.events))


def test_monitor_reaberto_com_vpn_no_ar_nao_redispara(system, monitor):
    monitor.connect("work")
    advance(system, monitor, lambda: monitor.state_of("work") == State.ON)
    events = []
    m2 = ConnectionMonitor(
        system, system, system.policy_reader, system, system, lambda k, p, d: events.append(k)
    )
    m2.poll()
    assert m2.state_of("work") == State.ON
    assert set(events) == {"changed"}


def test_monitor_queda_e_falha(system, monitor):
    monitor.connect("work")
    advance(system, monitor, lambda: monitor.state_of("work") == State.ON)
    monitor.disconnect("work")
    monitor.poll()
    assert ("down", "work", None) in monitor.events
    monitor.connect("quebrada")
    assert advance(system, monitor, lambda: monitor.state_of("quebrada") == State.ERROR)
    assert any(e[0] == "failed" and e[1] == "quebrada" for e in monitor.events)
    assert monitor.info("quebrada").untrusted_cert == "ab" * 32


def test_monitor_connect_derruba_a_outra(system, monitor):
    monitor.connect("work")
    advance(system, monitor, lambda: monitor.state_of("work") == State.ON)
    monitor.connect("quebrada")
    assert ("stop", "work") in system.calls
