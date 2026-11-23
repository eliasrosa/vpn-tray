"""Adaptadores reais, com executor de processos falso e pastas temporárias."""

import json

import pytest

from vpntray.adapters.filesystem import EtcProfileRepository, JsonPolicyReader, JsonSettingsRepository
from vpntray.adapters.pkexec import PkexecProfileAdmin
from vpntray.adapters.process import Result
from vpntray.adapters.systemd import JournalctlJournal, SystemdServiceManager, parse_unit_show
from vpntray.application.errors import AdminCancelled, AdminError, AuthenticationDenied, StartFailed
from vpntray.domain.model import NewProfile, Settings, UnitInfo


class FakeRunner:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        return self.results.pop(0) if self.results else Result(0, "", "")


# ------------------------------------------------------------------ systemd
def test_parse_unit_show_varias_units_e_ignora_outras():
    out = (
        "Id=vpn-tray@work.service\nActiveState=active\nInvocationID=abc\n\n"
        "Id=vpn-tray@lab-2.service\nActiveState=inactive\nInvocationID=\n\n"
        "Id=ssh.service\nActiveState=active\n"
    )
    assert parse_unit_show(out) == {"work": UnitInfo("active", "abc"), "lab-2": UnitInfo("inactive", "")}


def test_systemd_units_e_start_stop():
    run = FakeRunner(Result(0, "Id=vpn-tray@work.service\nActiveState=active\nInvocationID=i\n", ""))
    sm = SystemdServiceManager(run)
    assert sm.units(["work"]) == {"work": UnitInfo("active", "i")}
    assert sm.units([]) == {}
    sm.start("work")
    sm.stop("work")
    assert [c[0][:2] for c in run.calls[1:]] == [["systemctl", "start"], ["systemctl", "stop"]]
    assert run.calls[1][1]["timeout"] >= 120, "espera a caixinha de senha"


def test_systemd_start_mapeia_erros():
    with pytest.raises(AuthenticationDenied):
        SystemdServiceManager(FakeRunner(Result(1, "", "Interactive authentication required."))).start("w")
    with pytest.raises(StartFailed, match="boom"):
        SystemdServiceManager(FakeRunner(Result(1, "", "boom"))).start("w")


def test_journal():
    run = FakeRunner(Result(0, "a\nb\n", ""), Result(0, "log", ""))
    j = JournalctlJournal(run)
    assert j.invocation_lines("") == [] and j.invocation_lines("inv") == ["a", "b"]
    assert j.tail("work", 5) == "log"
    assert "_SYSTEMD_INVOCATION_ID=inv" in run.calls[0][0]


# --------------------------------------------------------------- arquivos
def test_profile_repository(tmp_path):
    (tmp_path / "work.args").write_text("VPN_AUTH=saml\nVPN_HOST=vpn.example.com\n")
    (tmp_path / "work.conf").write_text("password = nunca-lido\n")
    (tmp_path / "Ruim.args").write_text("VPN_AUTH=saml\n")
    repo = EtcProfileRepository(str(tmp_path))
    assert list(repo.list()) == ["work"]
    assert repo.list()["work"].host == "vpn.example.com"
    assert EtcProfileRepository(str(tmp_path / "nao-existe")).list() == {}


def test_settings_repository(tmp_path):
    repo = JsonSettingsRepository(str(tmp_path / "x" / "settings.json"))
    assert repo.load() == Settings()
    s = repo.load()
    s.default, s.agents.allow_connect = "work", False
    repo.save(s)
    assert json.loads((tmp_path / "x" / "settings.json").read_text())["agents"]["allow_connect"] is False
    assert repo.load().default == "work"
    (tmp_path / "x" / "settings.json").write_text("{quebrado")
    assert repo.load() == Settings(), "arquivo inválido volta ao padrão"


def test_policy_reader(tmp_path):
    p = tmp_path / "policy.json"
    assert JsonPolicyReader(str(p)).load().require_password_connect is False
    p.write_text('{"require_password_connect": true}')
    assert JsonPolicyReader(str(p)).load().require_password_connect is True


# ------------------------------------------------------------------ pkexec
def test_pkexec_admin(tmp_path):
    helper = tmp_path / "helper"
    helper.write_text("")
    run = FakeRunner(Result(0, "ok", ""), Result(126, "", ""), Result(1, "", "nome inválido"))
    admin = PkexecProfileAdmin(str(helper), run)
    admin.add(NewProfile("work", "vpn.example.com"))
    assert run.calls[0][0] == ["pkexec", str(helper), "add"]
    assert json.loads(run.calls[0][1]["input_text"])["host"] == "vpn.example.com"
    with pytest.raises(AdminCancelled):
        admin.remove("work")
    with pytest.raises(AdminError, match="nome inválido"):
        admin.set_require_password(True)


def test_pkexec_sem_instalacao(tmp_path):
    with pytest.raises(AdminError, match=r"install\.sh"):
        PkexecProfileAdmin(str(tmp_path / "nada")).trust("w", "ab" * 32)
