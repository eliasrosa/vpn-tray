"""`vpnctl setup-agents` num $HOME falso."""

import json
import os
import subprocess
import sys

from conftest import ROOT

VPNCTL = os.path.join(ROOT, "bin", "vpnctl")


def run(home, *args, path=None):
    env = dict(os.environ, HOME=str(home))
    if path:
        env["PATH"] = path
    return subprocess.run(
        [sys.executable, VPNCTL, "setup-agents", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_dry_run_nao_mexe_em_nada(tmp_path):
    (tmp_path / ".kiro" / "settings").mkdir(parents=True)
    r = run(tmp_path, "--kiro", "--dry-run", path="/usr/bin:/bin")
    assert r.returncode == 0 and "Kiro: MCP 'vpn-tray'" in r.stdout
    assert not (tmp_path / ".kiro" / "settings" / "mcp.json").exists()


def test_kiro_preserva_outros_servidores_e_desfaz(tmp_path):
    settings = tmp_path / ".kiro" / "settings"
    settings.mkdir(parents=True)
    mcp = settings / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"outro": {"command": "x"}}}))
    assert run(tmp_path, "--kiro").returncode == 0
    data = json.loads(mcp.read_text())["mcpServers"]
    assert set(data) == {"outro", "vpn-tray"}
    assert data["vpn-tray"]["args"] == ["mcp"]
    assert data["vpn-tray"]["autoApprove"] == ["vpn_status", "vpn_logs"]
    skill = tmp_path / ".kiro" / "skills" / "vpn-tray" / "SKILL.md"
    assert skill.is_symlink() and "name: vpn-tray" in skill.read_text()
    assert list(settings.glob("mcp.json.bak-vpn-tray-*")), "backup antes de mexer"
    assert run(tmp_path, "--kiro", "--remove").returncode == 0
    assert set(json.loads(mcp.read_text())["mcpServers"]) == {"outro"}
    assert not skill.exists()
