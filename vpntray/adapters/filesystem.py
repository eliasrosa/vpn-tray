"""Adaptadores de arquivo: perfis (.args), configurações e política."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..domain.model import Policy, ProfileMeta, Settings
from ..domain.openfortivpn import parse_args_file
from ..domain.rules import NAME_RE

DEFAULT_CONF_DIR = "/etc/openfortivpn"
DEFAULT_POLICY_FILE = "/etc/vpn-tray/policy.json"


def default_settings_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "vpn-tray", "settings.json")


class EtcProfileRepository:
    """Lista perfis pelos <nome>.args (0644, sem segredos)."""

    def __init__(self, conf_dir: str = DEFAULT_CONF_DIR):
        self.conf_dir = Path(conf_dir)

    def list(self) -> dict[str, ProfileMeta]:
        out: dict[str, ProfileMeta] = {}
        try:
            entries = sorted(self.conf_dir.iterdir())
        except OSError:
            return out
        for path in entries:
            name = path.stem
            if path.suffix != ".args" or not NAME_RE.match(name):
                continue
            try:
                meta = parse_args_file(path.read_text())
            except OSError:
                continue
            out[name] = ProfileMeta(name, meta.get("VPN_AUTH", "?"), meta.get("VPN_HOST", ""))
        return out


class JsonSettingsRepository:
    def __init__(self, path: str | None = None):
        self.path = Path(path or default_settings_path())

    def load(self) -> Settings:
        try:
            return Settings.from_dict(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)


class JsonPolicyReader:
    def __init__(self, path: str = DEFAULT_POLICY_FILE):
        self.path = Path(path)

    def load(self) -> Policy:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        return Policy(bool(data.get("require_password_connect")))
