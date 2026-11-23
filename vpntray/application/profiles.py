"""Casos de uso: cadastrar, importar, remover perfis e confiar em certificado."""

from __future__ import annotations

import os
import re

from ..domain.model import NewProfile
from ..domain.openfortivpn import parse_conf
from ..domain.rules import HASH_RE, NAME_RE, normalize_cert, validate_new_profile
from ..ports import ProfileAdmin, ProfileRepository, SettingsRepository
from .errors import InvalidProfile


def name_from_filename(path: str) -> str:
    base = os.path.basename(path).rsplit(".", 1)[0].lower()
    if base in ("", "config"):
        return ""
    return re.sub(r"[^a-z0-9_-]", "-", base).strip("-")[:32]


class ProfileService:
    def __init__(self, repo: ProfileRepository, admin: ProfileAdmin, settings: SettingsRepository):
        self.repo, self.admin, self.settings = repo, admin, settings

    def validate(self, profile: NewProfile) -> str | None:
        return validate_new_profile(profile, self.repo.list())

    def add(self, profile: NewProfile, *, make_default: bool = False) -> None:
        err = self.validate(profile)
        if err:
            raise InvalidProfile(err)
        self.admin.add(profile)
        if make_default:
            s = self.settings.load()
            s.default = profile.name
            self.settings.save(s)

    def parse_import(
        self, text: str, filename: str = "", name: str | None = None
    ) -> tuple[NewProfile, list[str]]:
        return parse_conf(text, name or name_from_filename(filename))

    def remove(self, name: str) -> None:
        if not NAME_RE.match(name):
            raise InvalidProfile("nome inválido")
        self.admin.remove(name)
        s = self.settings.load()
        if s.default == name:
            s.default = None
            self.settings.save(s)

    def trust(self, name: str, digest: str) -> None:
        digest = normalize_cert(digest)
        if not NAME_RE.match(name) or not HASH_RE.match(digest):
            raise InvalidProfile("perfil ou hash inválido")
        self.admin.trust(name, digest)
